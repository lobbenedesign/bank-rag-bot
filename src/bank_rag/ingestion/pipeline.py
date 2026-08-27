"""Scheduled job that syncs the bank's public website into the knowledge base.

Referenced by the `ingestion-worker` service in docker-compose.yml. Treats
the page URL as the document's source_id, so a no-index rule of type URL
(e.g. 'https://www.example-bank.it/promo/*') maps directly to what gets
skipped here and purged by ManageNoIndexRules if already indexed.

The URL list below is a placeholder — production should discover URLs from
the site's sitemap.xml rather than a hardcoded list, so new pages are picked
up automatically instead of requiring a code change per page.
"""
from __future__ import annotations

import asyncio
import logging

from bank_rag.di_container import build_ingest_document_use_case, build_noindex_registry, get_settings
from bank_rag.domain.entities import Audience
from bank_rag.ingestion.loaders.web_scraper import WebScraper

logger = logging.getLogger(__name__)


async def sync_urls(urls: list[str], allowed_domain: str) -> None:
    scraper = WebScraper(allowed_domain=allowed_domain)
    registry = build_noindex_registry()
    ingest = build_ingest_document_use_case()

    for url in urls:
        if await registry.is_excluded(url):
            logger.info("skipping_noindex_url url=%s", url)
            continue
        try:
            page = await scraper.fetch(url)
        except Exception:
            logger.exception("scrape_failed url=%s", url)
            continue
        try:
            await ingest.execute(
                source_id=url,
                title=page.title,
                segments=page.segments,
                audience=Audience.PUBLIC,
                uploaded_by="web-scraper",
            )
        except Exception:
            logger.exception("ingest_failed url=%s", url)


async def main() -> None:
    settings = get_settings()
    urls = [
        f"https://{settings.allowed_scrape_domain}/faq",
        f"https://{settings.allowed_scrape_domain}/conti",
    ]
    await sync_urls(urls, settings.allowed_scrape_domain)


if __name__ == "__main__":
    asyncio.run(main())
