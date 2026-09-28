from fastapi import APIRouter

from app.schemas.analysis import BugAnalysis
from app.schemas.bug import BugReportCreate
from app.services.bug_analyzer import analyze_bug_report


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
