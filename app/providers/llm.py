from abc import ABC, abstractmethod

from app.schemas.analysis import BugAnalysis
from app.schemas.bug import BugReportCreate


class LLMProvider(ABC):
    @abstractmethod
    def analyze_bug(self, bug: BugReportCreate) -> BugAnalysis:
        pass
