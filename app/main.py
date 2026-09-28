from fastapi import FastAPI


app = FastAPI(
    title="AI Bug Analyzer",
    description="A learning and portfolio project for structured bug analysis.",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return the application health status."""
    return {"status": "ok"}

