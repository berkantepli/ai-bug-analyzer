from io import BytesIO
import re

from fastapi import HTTPException, UploadFile
from openpyxl import load_workbook
import xlrd


FIELD_ALIASES = {
    "title": {"title", "bug title", "bug name"},
    "description": {"description", "bug description"},
    "steps_to_reproduce": {
        "steps to reproduce",
        "steps",
        "reproduction steps",
        "steps to reproduce the bug",
    },
    "expected_result": {
        "expected result",
        "expected behavior",
        "expected behaviour",
    },
    "actual_result": {
        "actual result",
        "actual behavior",
        "actual behaviour",
    },
    "severity": {
        "severity",
        "bug severity",
        "issue severity",
    },
    "priority": {
        "priority",
        "bug priority",
        "issue priority",
    },
    "category": {
        "category",
        "bug category",
        "issue category",
        "type",
        "bug type",
    },
}


REQUIRED_FIELDS = (
    "title",
    "description",
    "steps_to_reproduce",
    "expected_result",
    "actual_result",
)


def _normalize_header(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def _records_from_rows(rows: list[tuple[object, ...]]) -> list[dict]:
    if not rows:
        raise HTTPException(status_code=422, detail="The Excel file is empty.")

    headers = [_normalize_header(value) for value in rows[0]]
    indexes: dict[str, int] = {}
    for field, aliases in FIELD_ALIASES.items():
        match = next((i for i, header in enumerate(headers) if header in aliases), None)
        if match is not None:
            indexes[field] = match

    missing = [field for field in REQUIRED_FIELDS if field not in indexes]
    if missing:
        labels = ", ".join(field.replace("_", " ") for field in missing)
        raise HTTPException(
            status_code=422, detail=f"Missing required Excel columns: {labels}."
        )

    records = []
    for row_number, row in enumerate(rows[1:], start=2):
        values = {
            field: str(row[index]).strip()
            if index < len(row) and row[index] is not None
            else ""
            for field, index in indexes.items()
        }
        if not any(values.values()):
            continue
        missing_values = [
            field.replace("_", " ") for field in REQUIRED_FIELDS if not values[field]
        ]
        if missing_values:
            error = f"Missing required values: {', '.join(missing_values)}."
        else:
            error = None
        records.append({"row": row_number, "values": values, "error": error})

    if not records:
        raise HTTPException(
            status_code=422, detail="The Excel file contains no bug records."
        )
    return records


async def parse_bug_spreadsheet(file: UploadFile) -> list[dict]:
    filename = (file.filename or "").lower()
    content = await file.read()
    try:
        if filename.endswith(".xlsx"):
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
            try:
                rows = list(workbook.active.iter_rows(values_only=True))
            finally:
                workbook.close()
        elif filename.endswith(".xls"):
            workbook = xlrd.open_workbook(file_contents=content)
            sheet = workbook.sheet_by_index(0)
            rows = [tuple(sheet.row_values(index)) for index in range(sheet.nrows)]
        else:
            raise HTTPException(
                status_code=415,
                detail="Only .xlsx and .xls files are supported for batch analysis.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail="The uploaded Excel file could not be read."
        ) from exc

    return _records_from_rows(rows)
