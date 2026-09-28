# AI Bug Analyzer

AI Bug Analyzer is a learning and portfolio project for QA-focused, structured bug analysis. In later phases, it will accept software bug reports and use an LLM to produce validated analysis such as severity, priority, category, possible root cause, missing information, and suggested test scenarios.

This project deliberately treats LLM output as untrusted input. Planned quality controls include API contract tests, response-schema validation, enum validation, error handling, negative scenarios, and prompt regression tests.

## Current scope

The implementation currently contains only a FastAPI health endpoint and its automated test. Bug report processing, persistence, and LLM integration will be added incrementally.

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

Open `http://127.0.0.1:8000/health`. Expected response:

```json
{"status": "ok"}
```

Interactive API documentation is available at `http://127.0.0.1:8000/docs`.

## Run tests

```bash
python -m pytest
```
