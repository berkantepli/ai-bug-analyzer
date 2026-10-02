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
}


@router.get("/batch/progress")
def get_batch_progress():
    return batch_progress


async def process_batch_record(
    record: dict[str, str],
    semaphore: asyncio.Semaphore,
):
    bug = BugReportCreate(
        title=record["title"],
        description=record["description"],
        steps_to_reproduce=[
            step.strip()
            for step in record["steps_to_reproduce"].splitlines()
            if step.strip()
        ],
        expected_result=record["expected_result"],
        actual_result=record["actual_result"],
    )

    try:
        async with semaphore:
            analysis = await analyze_with_llm(bug)

        batch_progress["completed"] += 1

    except Exception:
        batch_progress["failed"] += 1
        raise

    analysis = analysis.model_dump()

    if record.get("severity"):
        analysis["severity"] = record["severity"].strip().upper()

    if record.get("priority"):
        analysis["priority"] = record["priority"].strip().upper()

    if record.get("category"):
        analysis["category"] = record["category"].strip()

    return {
        "title": bug.title,
        "analysis": analysis,
    }


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

    batch_progress["status"] = "processing"
    batch_progress["total"] = len(records)
    batch_progress["completed"] = 0
    batch_progress["failed"] = 0

    total = len(records)
    worker_count = calculate_worker_count(total)

    semaphore = asyncio.Semaphore(worker_count)

    tasks = [
        process_batch_record(
            record,
            semaphore,
        )
        for record in records
    ]

    results = await asyncio.gather(
        *tasks,
        return_exceptions=True,
    )

    bugs = []
    failed = 0

    for result in results:
        if isinstance(result, Exception):
            failed += 1
            continue

        bugs.append(result)

    batch_progress["status"] = "completed"

    return {
        "count": len(bugs),
        "total": total,
        "completed": len(bugs),
        "failed": failed,
        "workers": worker_count,
        "bugs": bugs,
    }
