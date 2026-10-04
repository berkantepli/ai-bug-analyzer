"""Split "Steps to Reproduce" text into steps, however they are written."""

import re


# A list marker at the start of a line: "1.", "1)", "1 -", "a)", "Step 3:",
# "Adım 2." or a bullet such as "-", "*" or "•". It must be followed by a
# space (or end the line), so values such as "1.5 GB", "10.0.0.1" or "-5"
# are kept as they are.
STEP_MARKER = re.compile(
    r"^\s*(?:"
    r"(?:step|adım|schritt)\s*\d+\s*[.):\-–]?"
    r"|\d{1,3}\s*[.):\-–]"
    r"|[a-zA-Z][.)]"
    r"|[-*•·–—▪►]"
    r")(?:\s+|$)",
    re.IGNORECASE,
)


def split_steps(text: str) -> list[str]:
    """One step per non-empty line, without its list marker."""
    steps = (STEP_MARKER.sub("", line, count=1).strip() for line in text.splitlines())
    return [step for step in steps if step]
