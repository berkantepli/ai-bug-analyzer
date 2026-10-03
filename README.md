# AI Bug Analyzer

A QA-focused tool that turns software bug reports into a structured analysis using a local vision-capable LLM (Ollama + Qwen3-VL). Analyze a single bug with optional screenshots, or a whole Excel file of bugs at once.

> **Note:** This is a learning and portfolio project. AI-generated analysis is a hypothesis and should be reviewed by a QA engineer before it is treated as a confirmed finding.

---

## Features

### Single bug analysis

Enter a title, description, steps to reproduce, expected result, actual result and optional screenshots. The result contains:

- **Severity** (`LOW` / `MEDIUM` / `HIGH` / `CRITICAL`) and **Priority** (`P1`–`P4`)
- **Category**, **Impact** and **Possible Root Cause**
- **Suggested Test Scenarios**: ID, category, type, scenario, expected result, purpose and priority
- **Missing Information** that would help investigate the bug
- **Confidence** (0.0–1.0)
- **Visual Evidence**: what the screenshot shows and how it relates to the report

If a screenshot shows a different page than the report describes, the report is still analyzed. The mismatch is explained in Visual Evidence and confidence is capped at 0.6.

Each text field can be up to 5,000 characters. Up to 5 screenshots of at most 10 MB each can be attached, in PNG, JPEG, WEBP, GIF or BMP format.

### Report language

The analysis is written in the language of the report (for example English, Turkish or German). Quoted UI text such as button labels or error messages does not change the detected language. Severity, priority and category always stay in English so results can be grouped across reports.

### Input checks

Low-quality input is rejected with a clear reason instead of producing a misleading analysis:

| Check | Example | Done by |
|---|---|---|
| Unreadable text | `Xq7#vL@`, `asdkj qweoiu`, `asdfasdf`, `aaaaaa` | Backend, before the LLM |
| Placeholder text | `test test`, `lorem ipsum`, `n/a` | Backend, before the LLM |
| Field longer than 5,000 characters | A pasted log file | Backend, before the LLM |
| Same text in two or more fields | Expected result = actual result | Backend, before the LLM |
| Not a meaningful bug report | Nonsense sentences, a cake recipe | LLM |

Short or vague reports about real software behavior (for example "It does not work") are still analyzed, with low confidence and a list of missing information.

### Batch analysis (Excel)

Upload an `.xlsx` or `.xls` file to analyze many bugs at once.

- **Never stops on a bad row.** Rows with missing values, unusable text or LLM errors are shown as **FAILED** with the reason, and the remaining bugs are still analyzed.
- **Duplicates are detected.** A bug identical to an earlier one (ignoring case, spacing and punctuation) is marked **DUPLICATE OF BUG N** and is not sent to the LLM again.
- **Stops when Ollama goes away.** If Ollama becomes unreachable, the remaining bugs are marked **NOT ANALYZED** instead of each waiting for a timeout, and a **Retry not analyzed bugs** button analyzes only those once Ollama is back.
- **Live progress** with elapsed time. Each browser tab tracks its own batch, so several batches can run at the same time.
- **Summary** of analyzed, failed and duplicate bugs, with severity, priority and category counts.

### Service diagnosis

The page shows whether the analysis service is available and keeps it up to date: it notices when Ollama stops and switches back to available on its own when Ollama returns. A diagnosis view checks Ollama, the required model and a real inference call, and suggests a fix for each failing step.

---

## Excel format

- The file must contain **a single sheet**; only the active sheet is read.
- Limits: at most **5 MB**, **2000 rows** in the sheet and **500 bug records**.
- The header row may be anywhere in the **first 20 rows**, so report titles or notes can sit above it.
- Header names are case- and punctuation-insensitive and must be in English:

| Field | Required | Accepted headers |
|---|---|---|
| Title | ✅ | Title, Bug Title, Bug Name |
| Description | ✅ | Description, Bug Description |
| Steps to Reproduce | ✅ | Steps to Reproduce, Steps, Reproduction Steps |
| Expected Result | ✅ | Expected Result, Expected Behavior |
| Actual Result | ✅ | Actual Result, Actual Behavior |
| Severity | – | Severity, Bug Severity, Issue Severity |
| Priority | – | Priority, Bug Priority, Issue Priority |
| Category | – | Category, Bug Category, Type, Bug Type |

When the optional Severity, Priority or Category columns are filled, their values replace the ones suggested by the LLM. Numbers, percentages and dates are read as displayed in Excel (`404`, `15%`, `2026-10-02`).

---

## How it works

```text
Bug report (+ screenshots)
        │
        ▼
Backend checks ──────────────▶ rejected: unreadable / placeholder / identical fields
        │
        ▼
LLM call 1: text only ───────▶ rejected: not a meaningful bug report
  detects the report language
  and judges whether the text is a bug report
        │
        ▼
LLM call 2: report + screenshots
  structured analysis in the detected language
        │
        ▼
Web interface
```

The model is forced to answer with JSON that matches a Pydantic schema, so every result has the same structure.

---

## Tech stack

- **Backend:** Python 3.9+, FastAPI, Pydantic, Uvicorn
- **LLM:** Ollama with `qwen3-vl:8b-instruct`
- **Frontend:** HTML, CSS and JavaScript in a single template
- **Excel:** openpyxl (`.xlsx`), xlrd (`.xls`)
- **Tests:** pytest, HTTPX

---

## Project structure

```text
app/
├── api/
│   ├── bugs.py              # /bugs endpoints: single, batch, batch progress
│   └── health.py            # /health endpoints and service diagnosis
├── schemas/
│   ├── analysis.py          # BugAnalysis result schema
│   └── bug.py               # BugReportCreate input schema
├── services/
│   ├── llm_analyzer.py      # Prompts and Ollama calls
│   ├── batch_analyzer.py    # Excel parsing, header detection, duplicates
│   └── readability.py       # Unreadable, placeholder and identical-field checks
├── static/images/logo.png
├── templates/index.html     # Web interface
├── config.py                # Ollama URL and model
└── main.py                  # FastAPI app
tests/                       # pytest suite (the LLM is mocked)
```

---

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/bugs/analyze` | Analyze one bug (form fields + optional `screenshots`) |
| `POST` | `/bugs/batch` | Analyze an Excel file (`file`, optional `batch_id`) |
| `POST` | `/bugs/batch/retry` | Analyze bugs again from an earlier batch result (JSON) |
| `GET` | `/bugs/batch/{batch_id}/progress` | Progress of a running batch |
| `GET` | `/health` | Application health |
| `GET` | `/health/ollama` | Light check that Ollama and the model are available (no inference) |
| `GET` | `/health/analysis` | Whether the analysis service is available |
| `GET` | `/health/analysis/diagnose` | Step-by-step diagnosis with suggested fixes |

Interactive API docs are available at `/docs` while the app is running.

---

## Setup

**1. Clone and install**

```bash
git clone https://github.com/berkantepli/ai-bug-analyzer.git
cd ai-bug-analyzer
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**2. Install Ollama and pull the model**

```bash
ollama pull qwen3-vl:8b-instruct
```

Ollama must be running at `http://127.0.0.1:11434`. The URL, model name and context window can be changed in `app/config.py`.

The app asks Ollama for a 16,384-token context window instead of its 4,096-token default, so reports with several screenshots fit. With this setting the model uses about 7.7 GB of memory instead of 5.8 GB.

**3. Run the app**

```bash
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>.

---

## Tests

```bash
pytest
```

The tests mock the LLM, so Ollama does not need to be running.

---

## Security

The app is built to run **locally for a single user**:

- It has **no authentication**. Keep the default host (`127.0.0.1`) and do not start it with `--host 0.0.0.0` on a shared network; anyone who can reach it could use your LLM.
- Requests from other websites to the analysis endpoints are rejected, so a page open in your browser cannot start analyses in the background.
- Uploads are limited in size and type, and Excel files are parsed with `defusedxml` to block XML bombs.
- Text from Ollama and the model is escaped before it is shown in the page.
- Bug reports can contain instructions aimed at the model (prompt injection). The prompts tell the model to ignore them, but analysis of reports written by others should not be trusted blindly.

---

## Limitations

- Analysis runs on a local 8B model: a single bug takes about 20–50 seconds, and a batch is processed bug by bug.
- Very large screenshots use many tokens; if a report and its screenshots still do not fit into the context window, the analysis is rejected with a message asking for fewer screenshots or a shorter text.
- Excel header names must be in English. Cell contents can be in any language.
- Formula cells are only read correctly if the file was saved by Excel (cached values).
- AI results are suggestions, not verified defects or confirmed root causes.

---

## Future improvements

- Jira and test management (Xray) integration
- Persistent analysis history and report export
- Clearer errors when Ollama is unavailable during single bug analysis

---

## License

Personal learning and portfolio project.
