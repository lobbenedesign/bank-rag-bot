"""Thin OpenTelemetry wrapper so use cases don't import the OTel SDK directly.

Every AnswerQuestion call is traced; combined with the router agent's tool
call log, this gives full request-level observability into which intent was
detected, which tools ran, and whether the answer was grounded — the trace
data doubles as the input for offline RAG evaluation (see observability/eval).
"""
from __future__ import annotations

from contextlib import contextmanager

from opentelemetry import trace

_tracer = trace.get_tracer("bank_rag")


@contextmanager
def trace_span(name: str, **attributes: str):
    with _tracer.start_as_current_span(name) as span:
        for key, value in attributes.items():
            span.set_attribute(key, value)
        yield span
