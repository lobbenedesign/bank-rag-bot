"""Offline evaluation harness: runs a golden Q&A dataset through AnswerQuestion
and scores faithfulness / answer relevance / context precision with RAGAS.

Run in CI on every change to prompts, chunking or retrieval config — this is
what turns "we believe the RAG works" into a number that regressions break.

Usage: python -m bank_rag.observability.eval.ragas_eval golden_dataset.jsonl
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass

from datasets import Dataset
from ragas import evaluate
from ragas.metrics import answer_relevancy, context_precision, faithfulness

from bank_rag.application.use_cases.answer_question import AnswerQuestion
from bank_rag.domain.entities import Conversation


@dataclass(frozen=True)
class GoldenCase:
    question: str
    ground_truth: str


def _load_dataset(path: str) -> list[GoldenCase]:
    with open(path, encoding="utf-8") as f:
        return [GoldenCase(**json.loads(line)) for line in f if line.strip()]


async def run(answer_question: AnswerQuestion, dataset_path: str) -> None:
    cases = _load_dataset(dataset_path)
    questions, answers, contexts, ground_truths = [], [], [], []

    for case in cases:
        answer = await answer_question.execute(Conversation(), case.question)
        questions.append(case.question)
        answers.append(answer.text)
        contexts.append([c.snippet for c in answer.citations])
        ground_truths.append(case.ground_truth)

    result = evaluate(
        Dataset.from_dict(
            {"question": questions, "answer": answers, "contexts": contexts, "ground_truth": ground_truths}
        ),
        metrics=[faithfulness, answer_relevancy, context_precision],
    )
    print(result)


if __name__ == "__main__":
    from bank_rag.di_container import build_answer_question_use_case

    asyncio.run(run(build_answer_question_use_case(), sys.argv[1]))
