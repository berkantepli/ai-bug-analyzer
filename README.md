# AI Bug Analyzer

A QA-focused tool that turns software bug reports into a structured analysis using a local vision-capable LLM (Ollama + Qwen3-VL). Analyze a single bug with optional screenshots, or a whole Excel or CSV file of bugs at once.

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
| Empty field or only spaces | A blank Expected Result | Backend, before the LLM |
| Unreadable text | `Xq7#vL@`, `asdkj qweoiu`, `asdfasdf`, `aaaaaa` | Backend, before the LLM |
| Placeholder text | `test test`, `lorem ipsum`, `n/a` | Backend, before the LLM |
| Field longer than 5,000 characters | A pasted log file | Backend, before the LLM |
| Same text in two or more fields | Expected result = actual result | Backend, before the LLM |
| Not a meaningful bug report | Nonsense sentences, a cake recipe | LLM |

Short or vague reports about real software behavior (for example "It does not work") are still analyzed, with low confidence and a list of missing information.

### Batch analysis (Excel and CSV)

Upload an `.xlsx`, `.xls` or `.csv` file to analyze many bugs at once.

- **Never stops on a bad row.** Rows with missing values, unusable text or LLM errors are shown as **FAILED** with the reason, and the remaining bugs are still analyzed.
- **Duplicates are detected.** A bug identical to an earlier one (ignoring case, spacing and punctuation) is marked **DUPLICATE OF BUG N** and is not sent to the LLM again.
- **Stops when Ollama goes away.** If Ollama becomes unreachable, the remaining bugs are marked **NOT ANALYZED** instead of each waiting for a timeout, and a **Retry not analyzed bugs** button analyzes only those once Ollama is back.
- **Live progress** with elapsed time. Each browser tab tracks its own batch, so several batches can run at the same time; their requests take turns at Ollama.
- **Can be cancelled.** Clear cancels a running analysis, and closing or reloading the page stops the batch on the server, so Ollama is not kept busy with results nobody sees.
- **Summary** of analyzed, failed, duplicate and not analyzed bugs, with severity, priority and category counts.

### Service diagnosis

The page shows whether the analysis service is available and keeps it up to date: it notices when Ollama stops and switches back to available on its own when Ollama returns. A diagnosis view checks Ollama, the required model and a real inference call, and suggests a fix for each failing step.

While the service is being checked or is unavailable, the analyze buttons are disabled; hovering over them shows why.

### Web interface

- Results live only in the page, so leaving or reloading it during an analysis asks for confirmation first.
- Single bug and batch results are kept separately, so both can run at once and switching modes shows each one's last result.
- Light and dark themes; the choice is remembered in the browser.

---

## Excel and CSV format

- The file must contain **a single sheet**; only the active sheet is read.
- CSV files may use commas, semicolons or tabs, in UTF-8 or Windows Turkish (cp1254) encoding.
- Hidden rows, including rows hidden by a filter, are skipped; the number of skipped rows is shown above the results.
- Password-protected files cannot be read; remove the password first.
- Limits: at most **5 MB**, **2000 rows** in the sheet and **500 bug records**.
- The header row may be anywhere in the **first 20 rows**, so report titles or notes can sit above it.
- The English headers below are recognized directly (case and punctuation do not matter). Headers in other languages or with other names (for example `Başlık`, `Beschreibung`) are matched by the LLM, which needs Ollama; the matching is shown above the results so it can be checked:

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

When the optional Severity or Priority columns are filled, their values replace the ones suggested by the LLM. Common values from tools such as Jira, Bugzilla, Azure DevOps and ServiceNow are mapped to the app's scale (for example `Blocker` → CRITICAL, `Major` → HIGH, `Highest` → P1, `Sev 2` → HIGH, Turkish `Yüksek` → HIGH); unknown values are ignored and the LLM's value is kept. A filled Category column replaces the LLM's category. Numbers, percentages and dates are read as displayed in Excel (`404`, `15%`, `2026-10-02`).

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
- **Excel and CSV:** openpyxl (`.xlsx`), xlrd (`.xls`), Python's csv module
- **Tests:** pytest, HTTPX

---

## Project structure

```text
app/
├── api/
│   ├── bugs.py              # /bugs endpoints: single, batch, retry, progress
│   └── health.py            # /health endpoints and service diagnosis
├── schemas/
│   ├── analysis.py          # BugAnalysis result schema
│   └── bug.py               # BugReportCreate input schema
├── services/
│   ├── llm_analyzer.py      # Prompts and Ollama calls
│   ├── batch_analyzer.py    # Excel/CSV parsing, header detection, duplicates
│   ├── excel_values.py      # Severity and priority value mapping
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
| `POST` | `/bugs/batch` | Analyze an Excel or CSV file (`file`, optional `batch_id`) |
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
- Unexpected errors return a generic message; the details are written only to the server log.
- Bug reports can contain instructions aimed at the model (prompt injection). The prompts tell the model to ignore them, but analysis of reports written by others should not be trusted blindly.

---

## Limitations

- Analysis runs on a local 8B model: a single bug takes about 20–50 seconds, so a large batch can take a long time. Ollama handles one request at a time, so a single bug analyzed during a batch waits for its turn.
- Very large screenshots use many tokens; if a report and its screenshots still do not fit into the context window, the analysis is rejected with a message asking for fewer screenshots or a shorter text.
- Matching non-English Excel headers needs Ollama and adds a few seconds; if the LLM cannot match every required column, the file is rejected.
- Formula cells are read from the results Excel stores when it saves a file. Files written by scripts often contain formulas without results; such rows are marked as failed with a request to open and save the file in Excel. Formulas are not calculated by the app itself.
- AI results are suggestions, not verified defects or confirmed root causes.

---

## Future improvements

- Jira and test management (Xray) integration
- Persistent analysis history and report export

---

## License

Personal learning and portfolio project.
