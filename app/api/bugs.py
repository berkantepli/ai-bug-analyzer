from fastapi import APIRouter, File, Form, UploadFile

from app.schemas.analysis import BugAnalysis
from app.schemas.bug import BugReportCreate
from app.services.bug_analyzer import analyze_bug_report
from app.services.llm_analyzer import analyze_with_llm
from app.services.batch_analyzer import parse_bug_spreadsheet


router = APIRouter(prefix="/bugs", tags=["bugs"])


@router.post("/")
def create_bug(bug: BugReportCreate):
    return {
        "message": "Bug report created successfully",
        "bug": bug,
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
    bugs = []

    for record in records:
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

        analysis = analyze_bug_report(bug)
        analysis = analysis.model_dump()

        if record.get("severity"):
            severity = record["severity"].strip().upper()

            severity_map = {
                "CRITICAL": "CRITICAL",
                "HIGH": "HIGH",
                "MEDIUM": "MEDIUM",
                "LOW": "LOW",
            }

            analysis["severity"] = severity_map.get(
                severity,
                severity,
            )

        if record.get("priority"):
            priority = record["priority"].strip().upper()

            priority_map = {
                "P1": "P1",
                "P2": "P2",
                "P3": "P3",
                "P4": "P4",
            }

            analysis["priority"] = priority_map.get(
                priority,
                priority,
            )

        if record.get("category"):
            analysis["category"] = record["category"].strip()

        bugs.append(
            {
                "title": bug.title,
                "analysis": analysis,
            }
        )

    return {"count": len(bugs), "bugs": bugs}
