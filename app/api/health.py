from urllib.error import URLError
from urllib.request import Request, urlopen
import json

from fastapi import APIRouter


router = APIRouter(
    prefix="/health",
    tags=["health"],
)


OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_TAGS_URL = f"{OLLAMA_URL}/api/tags"
OLLAMA_MODEL = "qwen3-vl:8b-instruct"


def check_ollama() -> dict:
    try:
        request = Request(
            OLLAMA_TAGS_URL,
            method="GET",
        )

        with urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))

        return {
            "status": "available",
            "reason": "Ollama is running and reachable.",
            "suggested_action": None,
            "models": data.get("models", []),
        }

    except (URLError, TimeoutError, OSError) as error:
        return {
            "status": "unavailable",
            "reason": (f"Could not connect to Ollama at {OLLAMA_URL}."),
            "suggested_action": (
                "Make sure Ollama is running and listening on port 11434."
            ),
            "models": [],
        }

    except (json.JSONDecodeError, ValueError):
        return {
            "status": "unavailable",
            "reason": "Ollama returned an invalid response.",
            "suggested_action": ("Restart Ollama and try the diagnosis again."),
            "models": [],
        }


def check_model(ollama_result: dict) -> dict:
    if ollama_result["status"] != "available":
        return {
            "status": "not_checked",
            "reason": "Ollama is unavailable, so the model could not be checked.",
            "suggested_action": "Fix the Ollama connection first.",
        }

    models = ollama_result.get("models", [])

    model_names = [model.get("name") for model in models if isinstance(model, dict)]

    if OLLAMA_MODEL in model_names:
        return {
            "status": "available",
            "reason": (f"{OLLAMA_MODEL} is installed and available."),
            "suggested_action": None,
        }

    return {
        "status": "unavailable",
        "reason": (f"The required model {OLLAMA_MODEL} was not found in Ollama."),
        "suggested_action": (f"Run: ollama pull {OLLAMA_MODEL}"),
    }


@router.get("")
def health_check() -> dict:
    """
    Basic application health check.

    This endpoint confirms that the FastAPI application
    itself is running.
    """
    return {
        "status": "ok",
    }


@router.get("/analysis")
def analysis_health() -> dict:
    """
    Quick health check for the analysis service.
    """

    ollama = check_ollama()
    model = check_model(ollama)

    available = ollama["status"] == "available" and model["status"] == "available"

    return {
        "available": available,
        "provider": "ollama",
        "model": OLLAMA_MODEL,
        "ollama": {
            "status": ollama["status"],
            "reason": ollama["reason"],
        },
        "model_status": model["status"],
    }


@router.get("/analysis/diagnose")
def diagnose_analysis_service() -> dict:
    """
    Detailed diagnostics for the complete analysis service.
    """

    ollama = check_ollama()
    model = check_model(ollama)

    ollama_available = ollama["status"] == "available"
    model_available = model["status"] == "available"

    analysis_available = ollama_available and model_available

    return {
        "available": analysis_available,
        "application": {
            "status": "available",
            "reason": "FastAPI application is running.",
            "suggested_action": None,
        },
        "ollama": {
            "status": ollama["status"],
            "reason": ollama["reason"],
            "suggested_action": ollama["suggested_action"],
        },
        "model": {
            "name": OLLAMA_MODEL,
            "status": model["status"],
            "reason": model["reason"],
            "suggested_action": model["suggested_action"],
        },
        "analysis_service": {
            "status": ("available" if analysis_available else "unavailable"),
            "reason": (
                "Ollama and the required model are available."
                if analysis_available
                else "One or more analysis dependencies are unavailable."
            ),
            "suggested_action": (
                None
                if analysis_available
                else "Run the diagnostics above and fix the first unavailable dependency."
            ),
        },
    }
