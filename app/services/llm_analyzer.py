import asyncio
import base64
import json
from typing import Optional
from urllib.request import Request, urlopen

from app.schemas.analysis import BugAnalysis
from app.schemas.bug import BugReportCreate


OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "qwen3-vl:8b-instruct"


def build_prompt(bug: BugReportCreate, has_screenshot: bool) -> str:
    screenshot_instruction = (
        """
A screenshot is provided.

IMPORTANT:
You MUST inspect the screenshot before completing the analysis.

The screenshot is part of the bug evidence and must be considered together
with the written bug report.

For visual_evidence:
- Describe concrete UI elements that are visibly present.
- Mention visible states such as disabled/enabled buttons, validation
  indicators, error messages, labels, fields, colors, or displayed values
  when relevant.
- Explain how the visible evidence relates to the reported bug.
- Do not invent anything that cannot be seen.
- Do not describe the screenshot generically.
- If the screenshot clearly provides relevant evidence, visual_evidence
  MUST contain a non-empty string.
- Only use null when the screenshot genuinely contains no useful evidence.

Visual evidence requirement:

If a screenshot is provided and it contains information relevant to the bug,
you MUST populate visual_evidence with a concrete description.

Do not return null simply because the textual bug report already contains
enough information.
"""
        if has_screenshot
        else """
No screenshot is provided.

The visual_evidence field must be null.
"""
    )

    return f"""
You are an experienced Software QA Engineer analyzing a bug report.

Analyze the following bug report and return ONLY valid JSON.

Do not return:
- Markdown
- Code fences
- Explanations outside JSON
- Reasoning
- Thinking process

Bug Title:
{bug.title}

Description:
{bug.description}

Steps to Reproduce:
{chr(10).join(bug.steps_to_reproduce)}

Expected Result:
{bug.expected_result}

Actual Result:
{bug.actual_result}

Your analysis must contain exactly these fields:

- severity
- priority
- category
- possible_root_cause
- suggested_test_scenarios
- missing_information
- confidence
- visual_evidence

Rules:

1. severity must be exactly one of:
   LOW
   MEDIUM
   HIGH
   CRITICAL

2. priority must be exactly one of:
   P1
   P2
   P3
   P4

3. category should describe the functional area of the bug.

4. possible_root_cause is a hypothesis, not a confirmed fact.
   Do not present assumptions as proven causes.

5. suggested_test_scenarios must contain useful QA test scenarios
   related to this bug.

6. missing_information must contain important information that is
   genuinely missing from the bug report.
   Do not leave it empty just because the fields exist.
   If additional information would materially help investigate the bug,
   list it.

7. confidence must be a number between 0.0 and 1.0.
   Do not use 1.0 unless the evidence is exceptionally clear.
   Do not use 0.0 unless there is almost no usable evidence.

8. {screenshot_instruction}

Return only the JSON object.
""".strip()


def _call_ollama(payload: dict) -> dict:
    request = Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    with urlopen(request, timeout=120) as response:
        response_data = response.read().decode("utf-8")

    return json.loads(response_data)


async def analyze_with_llm(
    bug: BugReportCreate,
    screenshots: Optional[list] = None,
) -> BugAnalysis:
    screenshots = screenshots or []

    images = []

    for screenshot in screenshots:
        image_bytes = await screenshot.read()

        if not image_bytes:
            continue

        images.append(base64.b64encode(image_bytes).decode("utf-8"))

    prompt = build_prompt(
        bug,
        has_screenshot=bool(images),
    )

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": images,
            }
        ],
        "stream": False,
        "format": BugAnalysis.model_json_schema(),
        "options": {
            "temperature": 0.1,
        },
    }

    response = await asyncio.to_thread(
        _call_ollama,
        payload,
    )

    content = response["message"]["content"]

    analysis_data = json.loads(content)

    return BugAnalysis.model_validate(analysis_data)
