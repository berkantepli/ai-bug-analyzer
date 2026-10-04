import logging
from typing import Awaitable, Callable, Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field, field_validator

from app.schemas.analysis import BugAnalysis
from app.schemas.bug import BugReportCreate

from app.services.llm_analyzer import (
    SPREADSHEET_FIELDS,
    ContextTooLargeError,
    InvalidBugReportError,
    OllamaUnavailableError,
    UnreadableScreenshotError,
    analyze_with_llm,
)
from app.services.batch_analyzer import (
    MAX_BUG_RECORDS,
    build_record,
    parse_bug_spreadsheet,
)
from app.services.excel_values import map_priority, map_severity
from app.services.readability import MAX_FIELD_CHARS

import asyncio
import re


router = APIRouter(prefix="/bugs", tags=["bugs"])

logger = logging.getLogger(__name__)


def calculate_worker_count(bug_count: int) -> int:
    if bug_count <= 10:
        return 1
    elif bug_count <= 50:
        return 2
    elif bug_count <= 200:
        return 3
    else:
        return 4


MAX_SCREENSHOTS = 5
MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024

# Image formats the vision model accepts, recognized by their first bytes
# rather than by the file name.
IMAGE_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"\xff\xd8\xff",  # JPEG
    b"GIF87a",
    b"GIF89a",
    b"BM",  # BMP
)


def _is_supported_image(data: bytes) -> bool:
    is_webp = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return is_webp or data.startswith(IMAGE_SIGNATURES)


async def _validate_screenshots(screenshots: list[UploadFile]) -> None:
    if len(screenshots) > MAX_SCREENSHOTS:
        raise HTTPException(
            status_code=422,
            detail=f"At most {MAX_SCREENSHOTS} screenshots can be uploaded.",
        )

    for screenshot in screenshots:
        data = await screenshot.read(MAX_SCREENSHOT_BYTES + 1)
        await screenshot.seek(0)

        if not data:
            continue

        name = screenshot.filename or "screenshot"
        if len(data) > MAX_SCREENSHOT_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Screenshot '{name}' is larger than "
                    f"{MAX_SCREENSHOT_BYTES // (1024 * 1024)} MB."
                ),
            )
        if not _is_supported_image(data):
            raise HTTPException(
                status_code=415,
                detail=(
                    f"Screenshot '{name}' is not a supported image "
                    "(PNG, JPEG, WEBP, GIF or BMP)."
                ),
            )


# Shown on every bug that was not analyzed because Ollama failed during the
# batch; the actual Ollama error is reported once in "stopped_reason".
NOT_ANALYZED_ERROR = (
    "The LLM could not analyze this bug: Ollama became unavailable during "
    "this batch, so this bug was not analyzed."
)


BATCH_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,100}")


# Progress of running batches, keyed by the batch id sent by each client,
# so batches started from different tabs do not share counters.
batch_progress: dict[str, dict] = {}


# Single bug analyses running in any tab; see get_activity.
running_single_analyses = 0


@router.get("/activity")
def get_activity():
    """What is running in any tab. Ollama analyzes one request at a time, so
    the page tells the user when a new analysis has to wait for another."""
    return {
        "batch_running": bool(batch_progress),
        "single_running": running_single_analyses > 0,
    }


@router.get("/batch/{batch_id}/progress")
def get_batch_progress(batch_id: str):
    progress = batch_progress.get(batch_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return progress


def to_bug_report(values: dict[str, str]) -> BugReportCreate:
    """Build the LLM input from form or Excel values; one step per line."""
    return BugReportCreate(
        title=values["title"],
        description=values["description"],
        steps_to_reproduce=[
            step.strip()
            for step in values["steps_to_reproduce"].splitlines()
            if step.strip()
        ],
        expected_result=values["expected_result"],
        actual_result=values["actual_result"],
    )


async def _analyze_unless_stopped(
    bug: BugReportCreate,
    stopped: asyncio.Event,
    screenshots: Optional[list[UploadFile]] = None,
) -> Optional[BugAnalysis]:
    """Analyze the bug, or return None as soon as the analysis is stopped.

    Without this, analyses already waiting on a hung Ollama would each wait
    for the full timeout after the first one has failed.
    """
    analysis = asyncio.ensure_future(analyze_with_llm(bug, screenshots))
    stop = asyncio.ensure_future(stopped.wait())
    try:
        await asyncio.wait({analysis, stop}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        stop.cancel()

    if analysis.done():
        return analysis.result()

    analysis.cancel()
    return None


# How often a running analysis checks whether the page is still waiting.
DISCONNECT_CHECK_SECONDS = 1


async def _stop_when_disconnected(request: Request, stopped: asyncio.Event) -> None:
    """Stop the analysis when the page that started it is closed or reloaded.

    The server would otherwise keep Ollama busy with results nobody sees,
    possibly for hours with a large batch.
    """
    while not stopped.is_set():
        if await request.is_disconnected():
            logger.info("Client disconnected; stopping %s", request.url.path)
            stopped.set()
            return
        await asyncio.sleep(DISCONNECT_CHECK_SECONDS)


async def process_batch_record(
    record: dict,
    semaphore: asyncio.Semaphore,
    progress: dict,
    batch_state: dict,
) -> dict:
    values = record["values"]
    result = {
        "row": record["row"],
        "status": "failed",
        "title": values.get("title", ""),
        "bug": values,
        "analysis": None,
        "error": record["error"],
        "duplicate_of": record["duplicate_of"],
    }

    # Rows rejected while reading the Excel file are counted up front.
    if result["error"]:
        return result

    # Repeated bugs are not sent to the LLM; the first occurrence is analyzed.
    if result["duplicate_of"]:
        result["status"] = "duplicate"
        return result

    def not_analyzed() -> dict:
        progress["not_analyzed"] += 1
        result["status"] = "not_analyzed"
        result["error"] = NOT_ANALYZED_ERROR
        return result

    stopped = batch_state["stopped"]

    try:
        bug = to_bug_report(values)

        async with semaphore:
            # Once Ollama is unreachable, the remaining bugs are not sent:
            # each one would fail the same way or wait for the full timeout.
            if stopped.is_set():
                return not_analyzed()

            analysis = await _analyze_unless_stopped(bug, stopped)
            if analysis is None:
                return not_analyzed()

    except OllamaUnavailableError as error:
        if not stopped.is_set():
            batch_state["ollama_error"] = str(error)
            stopped.set()
        return not_analyzed()

    except InvalidBugReportError as error:
        progress["failed"] += 1
        result["error"] = f"Not a valid bug report: {error}"
        return result

    except Exception as error:
        progress["failed"] += 1
        result["error"] = f"The LLM could not analyze this bug: {error}"
        return result

    progress["completed"] += 1

    analysis = analysis.model_dump()

    # Severity and priority from the Excel file win over the LLM when they
    # map to the app's scale; unknown values keep the LLM's suggestion.
    severity = map_severity(values.get("severity", ""))
    if severity:
        analysis["severity"] = severity

    priority = map_priority(values.get("priority", ""))
    if priority:
        analysis["priority"] = priority

    if values.get("category"):
        analysis["category"] = values["category"].strip()

    result["status"] = "analyzed"
    result["analysis"] = analysis
    return result


@router.post("/analyze", response_model=BugAnalysis)
async def analyze_bug(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    steps_to_reproduce: str = Form(...),
    expected_result: str = Form(...),
    actual_result: str = Form(...),
    screenshots: list[UploadFile] = File(default=[]),
):
    values = {
        "title": title,
        "description": description,
        "steps_to_reproduce": steps_to_reproduce,
        "expected_result": expected_result,
        "actual_result": actual_result,
    }
    # Same checks as an Excel row, including fields made only of spaces.
    error = build_record(0, values)["error"]
    if error:
        raise HTTPException(status_code=422, detail=error)

    await _validate_screenshots(screenshots)

    bug = to_bug_report(values)

    global running_single_analyses
    running_single_analyses += 1

    stopped = asyncio.Event()
    watcher = asyncio.ensure_future(_stop_when_disconnected(request, stopped))
    try:
        analysis = await _analyze_unless_stopped(bug, stopped, screenshots)
    except InvalidBugReportError as error:
        raise HTTPException(
            status_code=422, detail=f"Not a valid bug report: {error}"
        ) from error
    except UnreadableScreenshotError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except ContextTooLargeError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    # Ollama unreachable, timeouts or an unusable LLM answer; the message is
    # already written for users, the details are in the server log.
    except RuntimeError as error:
        raise HTTPException(
            status_code=503, detail=f"The LLM could not analyze this bug: {error}"
        ) from error
    finally:
        watcher.cancel()
        running_single_analyses -= 1

    if analysis is None:
        # Nobody receives this; the page was closed or the analysis cleared.
        raise HTTPException(status_code=499, detail="The request was cancelled.")
    return analysis


async def _run_batch(
    request: Request,
    batch_id: Optional[str],
    load_records: Callable[[], Awaitable[tuple[list[dict], dict]]],
) -> dict:
    """Analyze records with live progress; shared by batch and retry.

    load_records returns the records and details for the response, such as
    the Excel headers the LLM matched (detected_columns) and how many hidden
    rows were skipped (skipped_hidden_rows).
    """
    batch_id = batch_id or uuid4().hex
    if not BATCH_ID_PATTERN.fullmatch(batch_id):
        raise HTTPException(
            status_code=422,
            detail="batch_id must be 1-100 letters, digits, '-' or '_'.",
        )
    if batch_id in batch_progress:
        raise HTTPException(status_code=409, detail="Batch is already running.")

    progress = {
        "status": "reading",
        "total": 0,
        "completed": 0,
        "failed": 0,
        "rejected": 0,
        "duplicates": 0,
        "not_analyzed": 0,
    }
    batch_progress[batch_id] = progress

    try:
        records, details = await load_records()

        rejected = sum(1 for record in records if record["error"])
        duplicates = sum(1 for record in records if record["duplicate_of"])
        total = len(records)

        progress.update(
            status="processing",
            total=total,
            failed=rejected,
            rejected=rejected,
            duplicates=duplicates,
        )

        worker_count = calculate_worker_count(total)

        semaphore = asyncio.Semaphore(worker_count)
        batch_state = {"ollama_error": None, "stopped": asyncio.Event()}

        # Closing or reloading the page stops the batch like an Ollama
        # failure: bugs not started yet are not sent.
        watcher = asyncio.ensure_future(
            _stop_when_disconnected(request, batch_state["stopped"])
        )
        try:
            results = await asyncio.gather(
                *(
                    process_batch_record(record, semaphore, progress, batch_state)
                    for record in records
                )
            )
        finally:
            watcher.cancel()

        failed = sum(result["status"] == "failed" for result in results)
        not_analyzed = sum(result["status"] == "not_analyzed" for result in results)

        progress["status"] = "completed"

        return {
            "batch_id": batch_id,
            "total": total,
            "completed": total - failed - duplicates - not_analyzed,
            "failed": failed,
            "duplicates": duplicates,
            "not_analyzed": not_analyzed,
            "rejected": rejected,
            "workers": worker_count,
            # Set when the Excel headers were matched by the LLM.
            "detected_columns": details.get("detected_columns"),
            "skipped_hidden_rows": details.get("skipped_hidden_rows", 0),
            # Set when Ollama became unreachable and the batch stopped
            # sending the remaining bugs.
            "stopped_reason": (
                f"Ollama became unavailable during the batch: "
                f"{batch_state['ollama_error']}"
                if batch_state["ollama_error"]
                else None
            ),
            "bugs": results,
        }
    finally:
        batch_progress.pop(batch_id, None)


@router.post("/batch")
async def analyze_bug_batch(
    request: Request,
    file: UploadFile = File(...),
    batch_id: Optional[str] = Form(None),
):
    return await _run_batch(request, batch_id, lambda: parse_bug_spreadsheet(file))


class RetryBug(BaseModel):
    row: int
    bug: dict[str, str]

    @field_validator("bug")
    @classmethod
    def only_known_fields(cls, values: dict[str, str]) -> dict[str, str]:
        unknown = set(values) - set(SPREADSHEET_FIELDS)
        if unknown:
            raise ValueError(f"unknown fields: {', '.join(sorted(unknown))}")
        if any(len(value) > MAX_FIELD_CHARS for value in values.values()):
            raise ValueError(f"values must be at most {MAX_FIELD_CHARS} characters")
        return values


class RetryRequest(BaseModel):
    batch_id: Optional[str] = None
    bugs: list[RetryBug] = Field(min_length=1, max_length=MAX_BUG_RECORDS)


@router.post("/batch/retry")
async def retry_bug_batch(retry: RetryRequest, request: Request):
    """Analyze bugs again, typically those not analyzed when Ollama stopped.

    The values come from an earlier batch response, so the Excel file does
    not have to be uploaded again. They are validated like Excel rows.
    """

    async def load_records() -> tuple[list[dict], dict]:
        return [build_record(item.row, item.bug) for item in retry.bugs], {}

    return await _run_batch(request, retry.batch_id, load_records)
