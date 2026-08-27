"""FastAPI application factory. The only file allowed to import both
`interface.api.routers` and framework internals — every router below is a
thin adapter over the use-case layer, never containing business logic itself.

Also mounts the two static web UIs (interface/web/) — both are pure
presentation layers over the JSON API defined here: the admin panel and the
customer chat widget contain zero business logic of their own, only fetch()
calls against these same routes.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from bank_rag.interface.api.routers import admin_ingestion, admin_noindex, admin_urls, chat

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def create_app() -> FastAPI:
    app = FastAPI(title="Bank RAG Bot", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://www.example-bank.it"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(chat.router)
    app.include_router(admin_ingestion.router)
    app.include_router(admin_urls.router)
    app.include_router(admin_noindex.router)

    # Employee-only admin panel: not itself access-controlled at the static-
    # file level (that's a job for the reverse proxy / internal network in
    # production — e.g. VPN-only or IdP-gated ingress), but every API call
    # it makes is gated by identity.is_employee same as the JSON API above.
    app.mount("/admin-ui", StaticFiles(directory=_WEB_DIR / "admin", html=True), name="admin-ui")

    # Customer-facing chat widget + a local demo page showing how the bank
    # would embed it on their own site via a single <script> tag.
    app.mount("/widget", StaticFiles(directory=_WEB_DIR / "widget", html=True), name="widget")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
