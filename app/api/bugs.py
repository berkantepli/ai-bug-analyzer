from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.analysis import BugAnalysis
from app.schemas.bug import BugReportCreate

from app.services.llm_analyzer import InvalidBugReportError, analyze_with_llm
from app.services.batch_analyzer import parse_bug_spreadsheet
from app.services.readability import (
    field_length_error,
    identical_fields_error,
    readability_error,
)

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


# Progress of running batches, keyed by the batch id sent by each client,
# so batches started from different tabs do not share counters.
batch_progress: dict[str, dict] = {}


@router.get("/batch/{batch_id}/progress")
def get_batch_progress(batch_id: str):
    progress = batch_progress.get(batch_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Batch not found.")
    return progress


async def process_batch_record(
    record: dict,
    semaphore: asyncio.Semaphore,
    progress: dict,
) -> dict:
    values = record["values"]
    result = {
        "row": record["row"],
        "status": "failed",
        "title": values["title"],
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

    try:
        bug = BugReportCreate(
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

        async with semaphore:
            analysis = await analyze_with_llm(bug)

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

    if values.get("severity"):
        analysis["severity"] = values["severity"].strip().upper()

    if values.get("priority"):
        analysis["priority"] = values["priority"].strip().upper()

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
    error = (
        field_length_error(values)
        or readability_error(values)
        or identical_fields_error(values)
    )
    if error:
        raise HTTPException(status_code=422, detail=error)

    await _validate_screenshots(screenshots)

    bug = BugReportCreate(
        title=title,
        description=description,
        steps_to_reproduce=[
            step.strip() for step in steps_to_reproduce.splitlines() if step.strip()
        ],
        expected_result=expected_result,
        actual_result=actual_result,
    )

    try:
        return await analyze_with_llm(
            bug,
            screenshots,
        )
    except InvalidBugReportError as error:
        raise HTTPException(
            status_code=422, detail=f"Not a valid bug report: {error}"
        ) from error


@router.post("/batch")
async def analyze_bug_batch(
    file: UploadFile = File(...),
    batch_id: Optional[str] = Form(None),
):
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
    }
    batch_progress[batch_id] = progress

    try:
        records = await parse_bug_spreadsheet(file)

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

        results = await asyncio.gather(
            *(
                process_batch_record(record, semaphore, progress)
                for record in records
            )
        )

        failed = sum(result["status"] == "failed" for result in results)

        progress["status"] = "completed"

        return {
            "batch_id": batch_id,
            "total": total,
            "completed": total - failed - duplicates,
            "failed": failed,
            "duplicates": duplicates,
            "rejected": rejected,
            "workers": worker_count,
            "bugs": results,
        }
    finally:
        batch_progress.pop(batch_id, None)
