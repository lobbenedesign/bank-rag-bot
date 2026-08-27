"""Public source: periodic crawl of the bank's own website (FAQ, product pages).

Runs as a scheduled job (see docker-compose `ingestion-worker` service), not
inline with request handling — indexing latency is not user-facing latency.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from bank_rag.domain.entities import DocumentSegment
from bank_rag.ingestion.segmentation.html_segmenter import segment_html


@dataclass(frozen=True)
class ScrapedPage:
    url: str
    title: str
    segments: list[DocumentSegment]


class WebScraper:
    def __init__(self, allowed_domain: str, timeout_seconds: float = 10.0) -> None:
        self._allowed_domain = allowed_domain
        self._timeout = timeout_seconds

    async def fetch(self, url: str) -> ScrapedPage:
        if self._allowed_domain not in url:
            raise ValueError(f"refusing to scrape outside allowed domain: {url}")

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else url
        segments = segment_html(soup)
        return ScrapedPage(url=url, title=title, segments=segments)
