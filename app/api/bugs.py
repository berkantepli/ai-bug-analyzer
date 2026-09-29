from fastapi import APIRouter, File, UploadFile

from app.schemas.analysis import BugAnalysis
from app.schemas.bug import BugReportCreate
from app.services.bug_analyzer import analyze_bug_report
from app.services.batch_analyzer import parse_bug_spreadsheet


router = APIRouter(prefix="/bugs", tags=["bugs"])


@router.post("/")
def create_bug(bug: BugReportCreate):
    return {
        "message": "Bug report created successfully",
        "bug": bug,
    }


@router.post("/analyze", response_model=BugAnalysis)
def analyze_bug(bug: BugReportCreate):
    return analyze_bug_report(bug)


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
