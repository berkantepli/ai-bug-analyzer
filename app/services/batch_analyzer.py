from datetime import date, datetime, time
from io import BytesIO
from itertools import islice
import re

from fastapi import HTTPException, UploadFile
from openpyxl import load_workbook
import xlrd

from app.services.readability import (
    field_length_error,
    identical_fields_error,
    normalize_text,
    readability_error,
)


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


HEADER_SEARCH_ROWS = 20

# Upload limits that keep a single batch from exhausting memory or keeping
# the LLM busy for hours.
MAX_EXCEL_BYTES = 5 * 1024 * 1024
MAX_SHEET_ROWS = 2000
MAX_BUG_RECORDS = 500


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return format(value, ".15g")


def _format_datetime(value: datetime) -> str:
    if value.time() == time():
        return value.date().isoformat()
    timespec = "minutes" if value.second == 0 else "seconds"
    return value.isoformat(sep=" ", timespec=timespec)


def _format_cell(value: object, number_format: str = "General") -> object:
    """Render numbers, percentages and dates the way Excel displays them."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, datetime):
        return _format_datetime(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        if "%" in number_format:
            return f"{_format_number(value * 100)}%"
        return _format_number(value)
    return value


def _xls_cell_value(workbook: xlrd.book.Book, cell: xlrd.sheet.Cell) -> object:
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
        return None
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    if cell.ctype == xlrd.XL_CELL_DATE:
        return _format_cell(xlrd.xldate.xldate_as_datetime(cell.value, workbook.datemode))
    if cell.ctype == xlrd.XL_CELL_NUMBER:
        format_key = workbook.xf_list[cell.xf_index].format_key
        return _format_cell(cell.value, workbook.format_map[format_key].format_str)
    return cell.value


def _normalize_header(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower()).strip()


def _header_indexes(row: tuple[object, ...]) -> dict[str, int]:
    headers = [_normalize_header(value) for value in row]
    indexes: dict[str, int] = {}
    for field, aliases in FIELD_ALIASES.items():
        match = next((i for i, header in enumerate(headers) if header in aliases), None)
        if match is not None:
            indexes[field] = match
    return indexes


def _find_header(rows: list[tuple[object, ...]]) -> tuple[int, dict[str, int]]:
    """Find the header row, allowing report titles or notes above it."""
    best_row_index = 0
    best_indexes: dict[str, int] = {}
    best_score = 0
    for row_index, row in enumerate(rows[:HEADER_SEARCH_ROWS]):
        indexes = _header_indexes(row)
        score = sum(field in indexes for field in REQUIRED_FIELDS)
        if score > best_score:
            best_row_index, best_indexes, best_score = row_index, indexes, score
        if score == len(REQUIRED_FIELDS):
            break
    return best_row_index, best_indexes


def _records_from_rows(rows: list[tuple[object, ...]]) -> list[dict]:
    if not rows:
        raise HTTPException(status_code=422, detail="The Excel file is empty.")

    header_index, indexes = _find_header(rows)

    missing = [field for field in REQUIRED_FIELDS if field not in indexes]
    if missing:
        labels = ", ".join(field.replace("_", " ") for field in missing)
        raise HTTPException(
            status_code=422, detail=f"Missing required Excel columns: {labels}."
        )

    records = []
    for row_number, row in enumerate(
        rows[header_index + 1 :], start=header_index + 2
    ):
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
            error = (
                field_length_error(values)
                or readability_error(values)
                or identical_fields_error(values)
            )
        records.append(
            {"row": row_number, "values": values, "error": error, "duplicate_of": None}
        )

    if not records:
        raise HTTPException(
            status_code=422, detail="The Excel file contains no bug records."
        )

    if len(records) > MAX_BUG_RECORDS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"The Excel file contains {len(records)} bug records; "
                f"the maximum is {MAX_BUG_RECORDS}."
            ),
        )

    _mark_duplicates(records)
    return records


def _mark_duplicates(records: list[dict]) -> None:
    """Point repeated bugs at the 1-based number of their first occurrence."""
    first_seen: dict[tuple[str, ...], int] = {}
    for bug_number, record in enumerate(records, start=1):
        if record["error"]:
            continue
        key = tuple(
            normalize_text(record["values"][field]) for field in REQUIRED_FIELDS
        )
        if key in first_seen:
            record["duplicate_of"] = first_seen[key]
        else:
            first_seen[key] = bug_number


async def parse_bug_spreadsheet(file: UploadFile) -> list[dict]:
    filename = (file.filename or "").lower()
    content = await file.read(MAX_EXCEL_BYTES + 1)
    if len(content) > MAX_EXCEL_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"The Excel file is larger than {MAX_EXCEL_BYTES // (1024 * 1024)} MB.",
        )

    too_many_rows = HTTPException(
        status_code=422,
        detail=f"The Excel sheet has more than {MAX_SHEET_ROWS} rows.",
    )
    try:
        if filename.endswith(".xlsx"):
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
            try:
                rows = [
                    tuple(
                        _format_cell(cell.value, cell.number_format or "General")
                        for cell in row
                    )
                    for row in islice(
                        workbook.active.iter_rows(min_row=1), MAX_SHEET_ROWS + 1
                    )
                ]
            finally:
                workbook.close()
            if len(rows) > MAX_SHEET_ROWS:
                raise too_many_rows
        elif filename.endswith(".xls"):
            workbook = xlrd.open_workbook(file_contents=content, formatting_info=True)
            sheet = workbook.sheet_by_index(0)
            if sheet.nrows > MAX_SHEET_ROWS:
                raise too_many_rows
            rows = [
                tuple(_xls_cell_value(workbook, cell) for cell in sheet.row(index))
                for index in range(sheet.nrows)
            ]
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
