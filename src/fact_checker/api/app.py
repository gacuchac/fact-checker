"""The FastAPI app: wiring of settings, clients, routes, CORS and the built web app."""

import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import NamedTuple

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from fact_checker.corpus import load_corpus
from fact_checker.index import build_index
from fact_checker.llm.base import LLMClient
from fact_checker.llm.claude import ClaudeClient
from fact_checker.llm.config import Settings, settings_from_environment
from fact_checker.llm.openai_client import OpenAIClient
from fact_checker.store import init_store

from .routes import count_docs, health_router, router
from .security import RateLimiter

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "data" / "corpus.json"
DEFAULT_DB = ROOT / "data" / "factcheck.sqlite"
WEB_DIST = ROOT / "web" / "dist"
DEV_ORIGIN = "http://localhost:5173"


class Clients(NamedTuple):
    """The model client of each step."""

    decompose: LLMClient
    check: LLMClient
    verify: LLMClient
    review: LLMClient


def real_clients(settings: Settings) -> Clients:
    """Build Claude clients for decompose, falsifiability and verify and an OpenAI client for review from the keys in settings."""
    claude = ClaudeClient(settings.anthropic_api_key)
    return Clients(claude, claude, claude, OpenAIClient(settings.openai_api_key))


def _prepare_store(db: Path, corpus: Path) -> None:
    init_store(db)
    if count_docs(db) == 0:
        build_index(load_corpus(corpus), db)


def _spa_route(app: FastAPI, static_dir: Path) -> None:
    root = static_dir.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404)
        target = (root / path).resolve()
        if path and target.is_file() and target.is_relative_to(root):
            return FileResponse(target)
        return FileResponse(root / "index.html")


def create_app(
    settings: Settings,
    db: Path,
    make_clients: Callable[[Settings], Clients] = real_clients,
    static_dir: Path | None = None,
    corpus: Path = CORPUS,
) -> FastAPI:
    """Build the API app over the database db with the models from make_clients.

    All state (settings, db, clients, rate-limit buckets) lives on app.state. On startup the run store is
    created and, if the docs table is missing or empty, built from corpus (default data/corpus.json). When static_dir exists
    its files are served with a fallback to index.html for GET paths outside /api. CORS allows only the
    Vite dev origin.
    """

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        _prepare_store(db, corpus)
        yield

    app = FastAPI(title="fact-checker", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.clients = make_clients(settings)
    app.state.rate_limiter = RateLimiter()
    app.add_middleware(CORSMiddleware, allow_origins=[DEV_ORIGIN], allow_methods=["*"], allow_headers=["*"])
    app.include_router(health_router)
    app.include_router(router)
    if static_dir is not None and static_dir.is_dir():
        _spa_route(app, static_dir)
    return app


def create_app_from_env() -> FastAPI:
    """Build the app from the environment: settings from env and .env; paths from FC_DB, FC_WEB_DIST and FC_CORPUS.

    The defaults are data/factcheck.sqlite, web/dist (served only when it exists) and data/corpus.json in the
    source checkout; a deployment sets the variables when the package is installed elsewhere.
    """
    db = Path(os.environ.get("FC_DB", DEFAULT_DB))
    web_dist = Path(os.environ.get("FC_WEB_DIST", WEB_DIST))
    corpus = Path(os.environ.get("FC_CORPUS", CORPUS))
    static_dir = web_dist if web_dist.is_dir() else None
    return create_app(settings_from_environment(), db, static_dir=static_dir, corpus=corpus)
