# AI Bug Analyzer

AI-powered bug analysis tool built as a QA-focused learning and portfolio project.

AI Bug Analyzer takes a structured software bug report and analyzes it using a local vision-capable LLM. The goal is to turn raw bug reports into a structured QA analysis that helps testers and developers understand the issue, assess its impact, identify possible root causes, and generate relevant test scenarios.

> **Note:** This is a learning and portfolio project. AI-generated analysis should be reviewed and validated by a human QA engineer before being treated as a confirmed finding.

---

## Features

### 🐞 Structured Bug Analysis

Submit a bug report containing:

- Bug title
- Description
- Steps to reproduce
- Expected result
- Actual result
- Optional screenshots

The analyzer returns a structured QA-oriented result including:

- **Severity**
  - Low
  - Medium
  - High
  - Critical
- **Priority**
  - P1
  - P2
  - P3
  - P4
- **Category**
- **Possible Root Cause**
- **Suggested Test Scenarios**
- **Missing Information**
- **Confidence**
- **Visual Evidence**

The analysis output is presented through a dedicated UI rather than exposing the raw AI response.

---

### 🧪 QA-Focused Test Scenarios

The analyzer generates structured test scenarios instead of returning generic Positive / Negative labels.

Each scenario can include:

```text
TC-01

Functional Validation

Scenario
Enter valid card details and verify the Payment button becomes enabled.

Expected Result
Payment button should become enabled after all required fields pass validation.

Purpose
Verify that successful field validation correctly triggers the payment action.

Priority
High
```

This is intended to make the AI output more useful from a practical software testing perspective.

---

### 🖼️ Screenshot & Visual Evidence Analysis

Bug reports can include screenshots as additional evidence.

When a screenshot is provided, the vision-capable model is instructed to inspect the image together with the written bug report and return concrete visual evidence when relevant.

Examples of visual information that can be analyzed include:

- Visible error messages
- Button states
- Form validation states
- Labels and displayed values
- UI elements
- Enabled / disabled states
- Other visible evidence related to the reported issue

The system is instructed not to invent visual information that cannot be observed.

---

### 📊 Batch Bug Analysis

Multiple bug reports can be analyzed from an Excel file.

Supported formats:

- `.xlsx`
- `.xls`

The batch analyzer recognizes common column variations for:

- Title
- Description
- Steps to Reproduce
- Expected Result
- Actual Result

Batch analysis also provides:

- Number of bugs analyzed
- Progress percentage
- Completed / total bug count
- Elapsed analysis time
- Processing status
- Animated analysis status

Example:

```text
Analyzing...
━━━━━━━━━━━━━━━━━━━━━━ 60%

6 / 10 bugs analyzed
⏱ 00:42 elapsed
```

---

### 🔎 Analysis Service Diagnosis

The application includes a service diagnosis interface for checking the local analysis environment.

It can report the status of:

- Ollama
- Required model
- Inference availability

A **Retry Connection** action is also available to re-check the analysis service without refreshing the page.

---

## Tech Stack

### Backend

- Python
- FastAPI
- Pydantic
- Uvicorn

### AI / LLM

- Ollama
- Qwen3-VL 8B Instruct

The application communicates with the local Ollama API for bug analysis.

### Frontend

- HTML
- CSS
- JavaScript

### Data / File Processing

- OpenPyXL
- xlrd
- Excel `.xlsx` / `.xls`

### Testing

- Pytest
- HTTPX

---

## Architecture

The project follows a lightweight layered structure:

```text
ai-bug-analyzer/
│
├── app/
│   ├── api/
│   │   ├── bugs.py
│   │   └── health.py
│   │
│   ├── schemas/
│   │   ├── analysis.py
│   │   └── bug.py
│   │
│   ├── services/
│   │   ├── bug_analyzer.py
│   │   ├── llm_analyzer.py
│   │   └── batch_analyzer.py
│   │
│   ├── static/
│   │
│   └── templates/
│       └── index.html
│
├── tests/
│
├── main.py
├── requirements.txt
└── README.md
```

The FastAPI application exposes the bug analysis API under `/bugs` and serves the frontend from the application templates.

---

## Analysis Flow

```text
Bug Report
    │
    ├── Title
    ├── Description
    ├── Steps to Reproduce
    ├── Expected Result
    ├── Actual Result
    └── Screenshot (optional)
            │
            ▼
     FastAPI Backend
            │
            ▼
       Bug Analyzer
            │
            ▼
   Local Ollama / Qwen3-VL
            │
            ▼
    Structured QA Analysis
            │
            ├── Severity
            ├── Priority
            ├── Category
            ├── Root Cause
            ├── Test Scenarios
            ├── Missing Information
            ├── Confidence
            └── Visual Evidence
            │
            ▼
       Web Interface
```

The LLM prompt explicitly requires structured output and defines the expected analysis fields and severity / priority values.

---

## API

### Health Check

```http
GET /health
```

Returns the application health status.

### Analyze Bug

```http
POST /bugs/analyze
```

Analyzes a single bug report.

### Batch Analysis

```http
POST /bugs/batch
```

Accepts an Excel file and analyzes the contained bug reports.

### Create Bug

```http
POST /bugs/
```

Creates a bug report payload.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/berkantepli/ai-bug-analyzer.git
cd ai-bug-analyzer
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

#### macOS / Linux

```bash
source .venv/bin/activate
```

#### Windows

```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

The project currently uses FastAPI, Uvicorn, Pytest and HTTPX among its core dependencies.

---

## Ollama Setup

AI Bug Analyzer uses a local Ollama instance.

Install Ollama and make sure the required model is available:

```bash
ollama pull qwen3-vl:8b-instruct
```

Start Ollama and verify that the model is available before running the application.

The application currently targets:

```text
http://127.0.0.1:11434/api/chat
```

with:

```text
qwen3-vl:8b-instruct
```

as the configured model.

---

## Run the Application

Start the FastAPI application with:

```bash
uvicorn main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

---

## Testing

Run the test suite with:

```bash
pytest
```

---

## Example Input

```text
Bug Title:
Payment button remains disabled

Description:
The payment button does not become enabled after entering valid card details.

Steps to Reproduce:
1. Open the payment page.
2. Enter a valid card number.
3. Enter a valid expiration date.
4. Enter a valid CVV.
5. Observe the Payment button.

Expected Result:
The Payment button should become enabled.

Actual Result:
The Payment button remains disabled.
```

### Example Analysis

```text
Severity
High

Priority
P2

Category
Functional

Possible Root Cause
The payment form validation state may not be updated correctly after valid field input.

Suggested Test Scenarios

TC-01
Functional Validation

Scenario
Enter valid card details and verify the Payment button becomes enabled.

Expected Result
Payment button should become enabled after all required fields pass validation.

Purpose
Verify that successful field validation correctly triggers the payment action.

Priority
High
```

---

## Why I Built This

This project combines software testing knowledge with Python and AI/LLM experimentation.

The main objective is not to replace a QA engineer, but to explore how AI can assist with repetitive QA analysis tasks such as:

- Bug triage
- Severity and priority assessment
- Root-cause hypothesis generation
- Test scenario generation
- Bug report quality checks
- Screenshot-based evidence analysis
- Batch bug analysis

It also serves as a practical portfolio project for exploring the intersection of **Software QA, Python, API development, and AI/LLM applications**.

---

## Current Scope

The project currently focuses on:

- Structured bug analysis
- Local LLM inference
- Vision-based screenshot analysis
- QA-oriented test scenario generation
- Batch Excel analysis
- Analysis progress tracking
- Analysis service diagnosis
- Human-readable analysis results

AI-generated results are hypotheses and recommendations, not automatically verified defects or confirmed root causes.

---

## Future Improvements

Potential future improvements include:

- Jira integration
- Xray / test management integration
- Persistent analysis history
- Bug similarity / duplicate detection
- Improved test case generation
- Regression test recommendations
- API and database integration
- Automated report export
- Authentication and user management
- More advanced evaluation of AI analysis quality

---

## Project Status

🚧 **Active Development**

This project is continuously evolving as new QA and AI capabilities are added.

---

## License

This project is intended as a personal learning and portfolio project.