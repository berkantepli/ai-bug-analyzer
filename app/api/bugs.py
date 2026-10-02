from fastapi import APIRouter, File, Form, UploadFile

from app.schemas.analysis import BugAnalysis
from app.schemas.bug import BugReportCreate

from app.services.llm_analyzer import analyze_with_llm
from app.services.batch_analyzer import parse_bug_spreadsheet

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


batch_progress = {
    "status": "idle",
    "total": 0,
    "completed": 0,
    "failed": 0,
    "rejected": 0,
}


@router.get("/batch/progress")
def get_batch_progress():
    return batch_progress


async def process_batch_record(
    record: dict,
    semaphore: asyncio.Semaphore,
) -> dict:
    values = record["values"]
    result = {
        "row": record["row"],
        "status": "failed",
        "title": values["title"],
        "bug": values,
        "analysis": None,
        "error": record["error"],
    }

    # Rows rejected while reading the Excel file are counted up front.
    if result["error"]:
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

    except Exception as error:
        batch_progress["failed"] += 1
        result["error"] = f"The LLM could not analyze this bug: {error}"
        return result

    batch_progress["completed"] += 1

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
    bug = BugReportCreate(
        title=title,
        description=description,
        steps_to_reproduce=[
            step.strip() for step in steps_to_reproduce.splitlines() if step.strip()
        ],
        expected_result=expected_result,
        actual_result=actual_result,
    )

    return await analyze_with_llm(
        bug,
        screenshots,
    )


@router.post("/batch")
async def analyze_bug_batch(file: UploadFile = File(...)):
    records = await parse_bug_spreadsheet(file)

    rejected = sum(1 for record in records if record["error"])

    batch_progress["status"] = "processing"
    batch_progress["total"] = len(records)
    batch_progress["completed"] = 0
    batch_progress["failed"] = rejected
    batch_progress["rejected"] = rejected

    total = len(records)
    worker_count = calculate_worker_count(total)

    semaphore = asyncio.Semaphore(worker_count)

    results = await asyncio.gather(
        *(process_batch_record(record, semaphore) for record in records)
    )

    failed = sum(result["status"] == "failed" for result in results)

    batch_progress["status"] = "completed"

    return {
        "total": total,
        "completed": total - failed,
        "failed": failed,
        "workers": worker_count,
        "bugs": results,
    }
