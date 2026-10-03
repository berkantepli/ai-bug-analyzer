from urllib.error import URLError
from urllib.request import Request, urlopen
import json
import logging
import re

from fastapi import APIRouter

from app.config import OLLAMA_CONTEXT_LENGTH, OLLAMA_MODEL, OLLAMA_URL
from app.services.llm_analyzer import is_analyzing


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/health",
    tags=["health"],
)


OLLAMA_TAGS_URL = f"{OLLAMA_URL}/api/tags"

INFERENCE_TEST_ANSWER = "INFERENCE_TEST"

# Loading the model after Ollama starts can take well over 15 seconds on a
# machine with little free memory.
INFERENCE_TEST_TIMEOUT_SECONDS = 60


def check_ollama() -> dict:
    """
    Check whether Ollama is running and reachable.
    """

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

    except (URLError, TimeoutError, OSError):
        return {
            "status": "unavailable",
            "reason": f"Could not connect to Ollama at {OLLAMA_URL}.",
            "suggested_action": f"Make sure Ollama is running at {OLLAMA_URL}.",
            "models": [],
        }

    except (json.JSONDecodeError, ValueError):
        return {
            "status": "unavailable",
            "reason": "Ollama returned an invalid response.",
            "suggested_action": "Restart Ollama and try the diagnosis again.",
            "models": [],
        }


def check_model(ollama_result: dict) -> dict:
    """
    Check whether the required model is installed in Ollama.
    """

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
            "reason": f"{OLLAMA_MODEL} is installed and available.",
            "suggested_action": None,
        }

    return {
        "status": "unavailable",
        "reason": f"The required model {OLLAMA_MODEL} was not found in Ollama.",
        "suggested_action": f"Run: ollama pull {OLLAMA_MODEL}",
    }


def check_inference(ollama_result: dict, model_result: dict) -> dict:
    """
    Perform a real inference request against the required model.

    The test verifies:
    1. Ollama is available.
    2. The required model is available.
    3. Ollama actually used the required model.
    4. The model returned the expected test response.
    """

    if ollama_result["status"] != "available":
        return {
            "status": "not_checked",
            "reason": "Ollama is unavailable, so inference could not be tested.",
            "suggested_action": "Fix the Ollama connection first.",
        }

    if model_result["status"] != "available":
        return {
            "status": "not_checked",
            "reason": (
                "Inference test was skipped because the required model is unavailable."
            ),
            "suggested_action": "Make sure the required model is available first.",
        }

    # A test request would wait behind the running analyses and time out,
    # although the model is working.
    if is_analyzing():
        return {
            "status": "available",
            "reason": (
                f"{OLLAMA_MODEL} is busy analyzing bug reports, "
                "so the inference test was skipped."
            ),
            "suggested_action": None,
        }

    try:
        payload = json.dumps(
            {
                "model": OLLAMA_MODEL,
                "prompt": f"Reply with exactly: {INFERENCE_TEST_ANSWER}",
                "stream": False,
                "options": {
                    "num_ctx": OLLAMA_CONTEXT_LENGTH,
                    "temperature": 0,
                    "num_predict": 10,
                },
            }
        ).encode("utf-8")

        request = Request(
            f"{OLLAMA_URL}/api/generate",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
            },
        )

        with urlopen(request, timeout=INFERENCE_TEST_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))

        response_model = data.get("model")
        response_text = data.get("response", "").strip()

        # Verify that Ollama actually used the required model.
        if response_model != OLLAMA_MODEL:
            return {
                "status": "unavailable",
                "reason": (
                    f"Unexpected model returned: {response_model}. "
                    f"Expected: {OLLAMA_MODEL}."
                ),
                "suggested_action": (f"Make sure Ollama is using {OLLAMA_MODEL}."),
            }

        # Verify that the model actually generated the expected response,
        # tolerating case, spacing and punctuation such as a trailing period.
        if re.sub(r"[^A-Z_]", "", response_text.upper()) != INFERENCE_TEST_ANSWER:
            return {
                "status": "unavailable",
                "reason": (
                    "The model responded, but the inference test "
                    f"returned: {response_text or '[empty response]'}"
                ),
                "suggested_action": (
                    "Verify that the configured model is responding correctly."
                ),
            }

        return {
            "status": "available",
            "reason": (f"{OLLAMA_MODEL} successfully completed the inference test."),
            "suggested_action": None,
        }

    except (URLError, TimeoutError, OSError) as error:
        logger.warning("Inference health check failed: %s", error)
        return {
            "status": "unavailable",
            "reason": "The model inference request failed.",
            "suggested_action": ("Check Ollama and the model configuration."),
        }

    except (json.JSONDecodeError, ValueError) as error:
        logger.warning("Invalid inference health check response: %s", error)
        return {
            "status": "unavailable",
            "reason": "Ollama returned an invalid inference response.",
            "suggested_action": ("Restart Ollama and try the diagnosis again."),
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


def run_checks() -> tuple[dict, dict, dict]:
    """Check Ollama, the required model and inference, in that order."""
    ollama = check_ollama()
    model = check_model(ollama)
    inference = check_inference(ollama, model)
    return ollama, model, inference


def is_available(*results: dict) -> bool:
    return all(result["status"] == "available" for result in results)


@router.get("/ollama")
def ollama_health() -> dict:
    """
    Light check that Ollama is reachable and the model is installed.

    It sends no inference request, so the page can call it regularly to
    notice when Ollama stops.
    """

    ollama = check_ollama()
    model = check_model(ollama)

    return {"available": is_available(ollama, model)}


@router.get("/analysis")
def analysis_health() -> dict:
    """
    Quick health check for the complete analysis service.
    """

    ollama, model, inference = run_checks()

    return {
        "available": is_available(ollama, model, inference),
        "provider": "ollama",
        "model": OLLAMA_MODEL,
        "ollama": {
            "status": ollama["status"],
            "reason": ollama["reason"],
        },
        "model_status": model["status"],
        "inference_status": inference["status"],
    }


@router.get("/analysis/diagnose")
def diagnose_analysis_service() -> dict:
    """
    Detailed diagnostics for the complete analysis service.

    Diagnosis flow:

    Application
        ↓
    Ollama
        ↓
    Required Model
        ↓
    Inference
        ↓
    Analysis Service
    """

    ollama, model, inference = run_checks()

    return {
        "available": is_available(ollama, model, inference),
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
            # This is the fixed required model name.
            "name": OLLAMA_MODEL,
            "status": model["status"],
            "reason": model["reason"],
            "suggested_action": model["suggested_action"],
        },
        "inference": {
            "status": inference["status"],
            "reason": inference["reason"],
            "suggested_action": inference["suggested_action"],
        },
    }
