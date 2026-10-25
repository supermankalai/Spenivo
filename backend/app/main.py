import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging

logger = logging.getLogger("dailyspend")


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_for_runtime()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Optional sync backend for the Daily Spend app. All data is scoped to the authenticated user.",
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.middleware("http")
    async def request_log(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # Log the type only; exception messages may contain request data.
            logger.exception("unhandled error", extra={"request_id": request_id, "path": request.url.path})
            return JSONResponse(
                {"detail": "Internal server error"}, status_code=500, headers={"x-request-id": request_id}
            )
        # Path and status only — never bodies, query strings or headers.
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            },
        )
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/healthz", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)
    return app


app = create_app()
