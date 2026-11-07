"""FastAPI app. Run: uvicorn backend.api.main:app --reload   (from the project root)"""
from __future__ import annotations

import contextlib
import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config
from app.llm import LLMCapError, LLMError, calls_made
from backend.api.deps import ApiError
from backend.api.routes import cashflow, chat, contracts, obligations, penalty, sim, trust
from backend.api.routes import eval as eval_routes
from backend.api.schemas import Health

log = logging.getLogger("spa.api")


def _err(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Daily obligation recompute (APScheduler). Off when SPA_DISABLE_SCHEDULER=1."""
    sched = None
    if os.environ.get("SPA_DISABLE_SCHEDULER") != "1":
        from apscheduler.schedulers.background import BackgroundScheduler
        sched = BackgroundScheduler(daemon=True)
        sched.add_job(obligations.recompute_now, "cron", hour=6, minute=5, id="daily_obligations", replace_existing=True)
        sched.add_job(obligations.recompute_now, id="startup_obligations")      # once at startup
        sched.start()
    try:
        yield
    finally:
        if sched:
            sched.shutdown(wait=False)


def create_app() -> FastAPI:
    app = FastAPI(title="SPA Intelligence API", version="1.1.0", lifespan=lifespan,
                  description="Decision support, not legal advice.")
    app.add_middleware(GZipMiddleware, minimum_size=1024)   # text assets + JSON; ~70% smaller transfer
    app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=False,
                       allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        t0 = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "no-referrer"
        # method, path, status, duration only: never bodies, headers, contract text or keys
        log.info("%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - t0) * 1000)
        return response

    @app.exception_handler(ApiError)
    async def _api(_: Request, e: ApiError):
        return _err(e.status, e.code, e.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException):
        return _err(e.status_code, "not_found" if e.status_code == 404 else "http_error", str(e.detail))

    @app.exception_handler(RequestValidationError)
    async def _val(_: Request, e: RequestValidationError):
        # only field paths and messages; never echo the submitted values
        msg = "; ".join(f"{'.'.join(str(x) for x in err['loc'][1:])}: {err['msg']}" for err in e.errors()[:5])
        return _err(422, "validation_error", msg or "Invalid request.")

    @app.exception_handler(LLMCapError)
    async def _cap(_: Request, e: LLMCapError):
        return _err(429, "llm_cap_reached", str(e))

    @app.exception_handler(LLMError)
    async def _llm(_: Request, e: LLMError):
        return _err(503, "llm_unavailable", str(e)[:400])

    @app.exception_handler(Exception)
    async def _any(_: Request, e: Exception):
        log.error("unhandled %s", type(e).__name__)          # type only, no message (could hold contract text)
        return _err(500, "internal_error", "Something went wrong on the server.")

    for r in (contracts.router, penalty.router, cashflow.router, chat.router, eval_routes.router, trust.router, sim.router, obligations.router):
        app.include_router(r, prefix="/api")

    @app.get("/api/health", response_model=Health, tags=["meta"])
    def health():
        return Health(status="ok", llm_configured=config.llm_configured(), model=config.model_tag(),
                      llm_calls_made=calls_made(), llm_call_cap=config.MAX_LLM_CALLS)

    if config.SERVE_FRONTEND and (config.FRONTEND_DIST / "index.html").exists():
        dist = config.FRONTEND_DIST
        class ImmutableAssets(StaticFiles):
            """Vite emits content-hashed filenames under /assets, so they can be cached for a year."""

            async def get_response(self, path, scope):
                resp = await super().get_response(path, scope)
                if resp.status_code == 200:
                    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
                return resp

        if (dist / "assets").exists():
            app.mount("/assets", ImmutableAssets(directory=dist / "assets"), name="assets")
        if (dist / "media").exists():
            app.mount("/media", StaticFiles(directory=dist / "media"), name="media")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            if path.startswith("api/"):
                return _err(404, "not_found", "Not found.")
            f = (dist / path).resolve()
            if path and f.is_file() and dist.resolve() in f.parents:
                return FileResponse(f)
            return FileResponse(dist / "index.html")

    return app


app = create_app()
