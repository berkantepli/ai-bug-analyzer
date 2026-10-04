"""Map severity and priority values from Excel files to the app's scale.

Excel files exported from tools such as Jira, Bugzilla, Azure DevOps or
ServiceNow use their own words and numbers. Known values are mapped to
CRITICAL/HIGH/MEDIUM/LOW and P1-P4; anything else returns None, so the
value suggested by the LLM is kept instead of an unknown one.
"""

import re
import unicodedata
from typing import Optional


def _fold(value: str) -> str:
    """Lowercase, drop accents (Yüksek -> yuksek) and punctuation."""
    text = unicodedata.normalize("NFKD", value.casefold().replace("ı", "i"))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def _word_map(levels: dict[str, list[str]]) -> dict[str, str]:
    return {_fold(word): level for level, words in levels.items() for word in words}


SEVERITY_WORDS = _word_map(
    {
        "CRITICAL": [
            "Critical", "Blocker", "Showstopper", "Show-stopper", "Urgent",
            "Emergency", "Immediate", "Fatal", "Kritik", "Engelleyici", "Acil",
        ],
        "HIGH": ["High", "Highest", "Major", "Severe", "Important", "Yüksek", "Önemli"],
        "MEDIUM": ["Medium", "Normal", "Moderate", "Average", "Orta"],
        "LOW": [
            "Low", "Lowest", "Minor", "Trivial", "Cosmetic",
            "Düşük", "Çok düşük", "En düşük",
        ],
    }
)

PRIORITY_WORDS = _word_map(
    {
        "P1": [
            "Highest", "Critical", "Blocker", "Urgent", "Immediate",
            "Acil", "Kritik", "En yüksek",
        ],
        "P2": ["High", "Major", "Important", "Yüksek", "Önemli"],
        "P3": ["Medium", "Normal", "Moderate", "Orta"],
        "P4": ["Low", "Lowest", "Minor", "Trivial", "Planning", "Düşük", "En düşük"],
    }
)

# In these tools 1 is the most severe or urgent level; 0 (P0) and 5 (P5,
# "5 - Planning") fall on the ends of the four-level scale.
SEVERITY_NUMBERS = {1: "CRITICAL", 2: "HIGH", 3: "MEDIUM", 4: "LOW", 5: "LOW"}
PRIORITY_NUMBERS = {0: "P1", 1: "P1", 2: "P2", 3: "P3", 4: "P4", 5: "P4"}

# "1", "S1", "Sev 2", "P0", "Severity 3" or "1 - Critical".
NUMBERED_VALUE = re.compile(
    r"(?:p|s|sev|severity|prio|priority)?\s*(\d+)(?:\s+(.+))?"
)


def _map_value(
    value: str, words: dict[str, str], numbers: dict[int, str]
) -> Optional[str]:
    key = _fold(value)
    if not key:
        return None
    if key in words:
        return words[key]

    match = NUMBERED_VALUE.fullmatch(key)
    if match is None:
        return None

    number, label = match.groups()
    # "1 - Critical": the word is clearer than the tool-specific number.
    if label and label in words:
        return words[label]
    return numbers.get(int(number))


def map_severity(value: str) -> Optional[str]:
    return _map_value(value, SEVERITY_WORDS, SEVERITY_NUMBERS)


def map_priority(value: str) -> Optional[str]:
    return _map_value(value, PRIORITY_WORDS, PRIORITY_NUMBERS)
