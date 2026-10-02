from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.bugs import router as bugs_router
from app.api.health import router as health_router


app = FastAPI(
    title="AI Bug Analyzer",
    description="A learning and portfolio project for structured bug analysis.",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(bugs_router)
app.include_router(health_router)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    html_path = Path(__file__).parent / "templates" / "index.html"
    return html_path.read_text(encoding="utf-8")
