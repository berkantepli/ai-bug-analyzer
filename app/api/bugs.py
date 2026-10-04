from typing import Awaitable, Callable, Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.schemas.analysis import BugAnalysis
from app.schemas.bug import BugReportCreate

from app.services.llm_analyzer import (
    ContextTooLargeError,
    InvalidBugReportError,
    OllamaUnavailableError,
    analyze_with_llm,
)
from app.services.batch_analyzer import (
    MAX_BUG_RECORDS,
    build_record,
    parse_bug_spreadsheet,
)
from app.services.excel_values import map_priority, map_severity

import asyncio


router = APIRouter(prefix="/bugs", tags=["bugs"])


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


# Progress of running batches, keyed by the batch id sent by each client,
# so batches started from different tabs do not share counters.
batch_progress: dict[str, dict] = {}


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
    bug: BugReportCreate, stopped: asyncio.Event
) -> Optional[BugAnalysis]:
    """Analyze the bug, or return None as soon as the batch is stopped.

    Without this, analyses already waiting on a hung Ollama would each wait
    for the full timeout after the first one has failed.
    """
    analysis = asyncio.ensure_future(analyze_with_llm(bug))
    stop = asyncio.ensure_future(stopped.wait())
    try:
        await asyncio.wait({analysis, stop}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        stop.cancel()

    if analysis.done():
        return analysis.result()

    analysis.cancel()
    return None


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

    try:
        return await analyze_with_llm(
            bug,
            screenshots,
        )
    except InvalidBugReportError as error:
        raise HTTPException(
            status_code=422, detail=f"Not a valid bug report: {error}"
        ) from error
    except ContextTooLargeError as error:
        raise HTTPException(status_code=413, detail=str(error)) from error
    # Ollama unreachable, timeouts or an unusable LLM answer; the message is
    # already written for users, the details are in the server log.
    except RuntimeError as error:
        raise HTTPException(
            status_code=503, detail=f"The LLM could not analyze this bug: {error}"
        ) from error


async def _run_batch(
    batch_id: Optional[str],
    load_records: Callable[[], Awaitable[tuple[list[dict], Optional[dict]]]],
) -> dict:
    """Analyze records with live progress; shared by batch and retry.

    load_records returns the records and, when the LLM matched the Excel
    columns, the header used for each field.
    """
    batch_id = batch_id or uuid4().hex
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
        records, detected_columns = await load_records()

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

        results = await asyncio.gather(
            *(
                process_batch_record(record, semaphore, progress, batch_state)
                for record in records
            )
        )

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
            "detected_columns": detected_columns,
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
    file: UploadFile = File(...),
    batch_id: Optional[str] = Form(None),
):
    return await _run_batch(batch_id, lambda: parse_bug_spreadsheet(file))


class RetryBug(BaseModel):
    row: int
    bug: dict[str, str]


class RetryRequest(BaseModel):
    batch_id: Optional[str] = None
    bugs: list[RetryBug] = Field(min_length=1, max_length=MAX_BUG_RECORDS)


@router.post("/batch/retry")
async def retry_bug_batch(request: RetryRequest):
    """Analyze bugs again, typically those not analyzed when Ollama stopped.

    The values come from an earlier batch response, so the Excel file does
    not have to be uploaded again. They are validated like Excel rows.
    """

    async def load_records() -> tuple[list[dict], None]:
        return [build_record(item.row, item.bug) for item in request.bugs], None

    return await _run_batch(request.batch_id, load_records)
