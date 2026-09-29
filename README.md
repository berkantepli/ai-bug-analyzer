# AI Bug Analyzer

AI Bug Analyzer is a QA-focused learning and portfolio project designed to analyze software bug reports and generate structured QA insights.

The project is being developed incrementally, starting with the user interface and analysis workflow before integrating the LLM-powered analysis layer.

## Current Scope

The current implementation includes:

- Analysis service health status indicator
- Single Bug analysis mode
- Batch Analysis mode
- Single Bug bug-report form
- Bug title, description, steps to reproduce, expected result, and actual result fields
- Screenshot upload with multiple screenshot support
- Screenshot previews with individual removal
- Batch bug report upload and parsing for Excel (`.xlsx`, `.xls`) files
- Batch results showing each report's title, description, reproduction steps, expected result, and actual result
- Clear and Analyze actions for both analysis modes
- Batch Analyze action disabled until a file is selected
- Dark/light theme support

Batch Analysis reads the first worksheet and expects columns for Bug Title, Description, Steps to Reproduce, Expected Result, and Actual Result. It extracts and displays the records without LLM analysis.

## Planned Analysis

The planned analysis layer will use an LLM to generate structured QA insights from bug reports.

Potential analysis outputs include:

- Severity
- Priority
- Bug category
- Possible root cause
- Suggested test scenarios
- Additional QA insights

LLM output will be treated as untrusted input and validated before being used by the application.

## Planned Batch Analysis

Batch Analysis will allow users to upload structured bug reports and process multiple bugs in a single operation.

Input formats currently exposed by the UI:

- `.xlsx`
- `.xls`

Excel files are parsed and displayed as batch results. LLM analysis is planned for a later stage.

## Quality & Validation

Planned quality controls include:

- API contract tests
- Response schema validation
- Enum validation
- Error handling
- Negative scenario testing
- Prompt regression tests
- Validation of LLM-generated output

## Prerequisites

- Python 3.9+

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the API

```bash
uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok"}
```

Interactive API documentation:

```text
http://127.0.0.1:8000/docs
```

## Run Tests

```bash
python -m pytest
```
