import logging
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.bugs import router as bugs_router
from app.api.health import router as health_router


app = FastAPI(
    title="AI Bug Analyzer",
    description="A learning and portfolio project for structured bug analysis.",
    version="0.1.0",
)

# Relative to this file, so the app also starts from another directory.
APP_DIR = Path(__file__).parent

app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")

logger = logging.getLogger(__name__)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
    """Answer unexpected errors with JSON the page can show; details are logged."""
    logger.exception("Unexpected error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Unexpected server error. The details are in the server log."
        },
    )

# Endpoints that start LLM work; other websites must not trigger them
# through the user's browser.
PROTECTED_PATH_PREFIXES = ("/bugs", "/health/analysis")


class RejectCrossSiteRequests:
    """Plain ASGI middleware: unlike @app.middleware("http"), it lets the
    endpoints notice when the page closes the connection."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith(
            PROTECTED_PATH_PREFIXES
        ):
            # Browsers label every request with where it came from; API
            # clients such as curl send neither header and are not affected.
            headers = Headers(scope=scope)
            fetch_site = headers.get("sec-fetch-site")
            origin = headers.get("origin")
            from_other_site = fetch_site in ("cross-site", "same-site")
            foreign_origin = (
                origin is not None and urlsplit(origin).netloc != headers.get("host")
            )
            if from_other_site or foreign_origin:
                response = JSONResponse(
                    status_code=403,
                    content={"detail": "Requests from other websites are not allowed."},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


app.add_middleware(RejectCrossSiteRequests)


app.include_router(bugs_router)
app.include_router(health_router)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    html_path = APP_DIR / "templates" / "index.html"
    return html_path.read_text(encoding="utf-8")
