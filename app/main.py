from fastapi import FastAPI

from app.api.bugs import router as bugs_router


app = FastAPI(
    title="AI Bug Analyzer",
    description="A learning and portfolio project for structured bug analysis.",
    version="0.1.0",
)

app.include_router(bugs_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return the application health status."""
    return {"status": "ok"}
