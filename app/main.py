import logging
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.bugs import router as bugs_router
from app.api.health import router as health_router


app = FastAPI(
    title="AI Bug Analyzer",
    description="A learning and portfolio project for structured bug analysis.",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

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


@app.middleware("http")
async def reject_cross_site_requests(request: Request, call_next):
    if request.url.path.startswith(PROTECTED_PATH_PREFIXES):
        # Browsers label every request with where it came from; API clients
        # such as curl send neither header and are not affected.
        fetch_site = request.headers.get("sec-fetch-site")
        origin = request.headers.get("origin")
        from_other_site = fetch_site in ("cross-site", "same-site")
        foreign_origin = (
            origin is not None
            and urlsplit(origin).netloc != request.headers.get("host")
        )
        if from_other_site or foreign_origin:
            return JSONResponse(
                status_code=403,
                content={"detail": "Requests from other websites are not allowed."},
            )

    return await call_next(request)


app.include_router(bugs_router)
app.include_router(health_router)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    html_path = Path(__file__).parent / "templates" / "index.html"
    return html_path.read_text(encoding="utf-8")
