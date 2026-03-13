"""Validate docs/mimic_schema_reference.md against local MIMIC CSV.gz files.

This test requires local MIMIC data and is excluded from the default test run.
Run explicitly with: uv run pytest tests/test_schema_reference.py -m schema -v
"""

import re
from pathlib import Path

import pytest

from mimic_explorer.config import DATASETS
from mimic_explorer.db import column_info, get_connection

SCHEMA_DOC = Path(__file__).parent.parent / "docs" / "mimic_schema_reference.md"

# Section headers that delimit version-specific schema blocks
_SECTION_MIMIC4 = "## MIMIC-IV tables and columns"
_SECTION_MIMIC4_NOTE = "## MIMIC-IV-Note tables and columns"
_SECTION_MIMIC3 = "## MIMIC-III tables and columns"

# Matches lines like:
#   **hosp/patients**: subject_id, gender, anchor_age, ...
#   **PATIENTS**: ROW_ID, SUBJECT_ID, GENDER, ...
#   - **d_icd_diagnoses**: icd_code, icd_version, long_title
_TABLE_PATTERN = re.compile(r"^-?\s*\*\*(?:[\w/]+?/)?([\w]+)\*\*:\s*(.+)$")


def _parse_section(text: str, start_header: str, stop_headers: list[str]) -> dict[str, set[str]]:
    """Parse table -> column sets from a specific section of the schema doc."""
    tables: dict[str, set[str]] = {}
    in_section = False

    for line in text.splitlines():
        stripped = line.strip()
        if stripped == start_header:
            in_section = True
            continue
        if in_section and any(stripped == h for h in stop_headers):
            break
        if not in_section:
            continue
        m = _TABLE_PATTERN.match(stripped)
        if m:
            table_name = m.group(1).lower()
            columns = {c.strip().lower() for c in m.group(2).split(",")}
            tables[table_name] = columns
    return tables


def _get_actual_columns(dataset_key: str) -> dict[str, set[str]]:
    """Get actual column sets from local CSV.gz files."""
    ds = DATASETS[dataset_key]
    conn = get_connection()
    result: dict[str, set[str]] = {}

    for name, path in ds.find_tables().items():
        cols = column_info(conn, path)
        result[name] = {c["name"].lower() for c in cols}

    return result


def _compare(documented: dict[str, set[str]], actual: dict[str, set[str]]) -> list[str]:
    """Compare documented vs actual schemas, return list of error strings."""
    errors = []
    for table_name, actual_cols in sorted(actual.items()):
        if table_name not in documented:
            errors.append(f"  {table_name}: not documented")
            continue
        doc_cols = documented[table_name]
        missing_from_doc = actual_cols - doc_cols
        extra_in_doc = doc_cols - actual_cols
        if missing_from_doc:
            errors.append(f"  {table_name}: undocumented columns: {sorted(missing_from_doc)}")
        if extra_in_doc:
            errors.append(f"  {table_name}: documented but not in file: {sorted(extra_in_doc)}")
    return errors


@pytest.mark.schema
def test_mimic3_schema_matches_reference():
    ds = DATASETS.get("mimic-iii")
    if not ds or not ds.base_path.exists():
        pytest.skip("MIMIC-III data not available locally")

    text = SCHEMA_DOC.read_text()
    documented = _parse_section(text, _SECTION_MIMIC3, [])
    actual = _get_actual_columns("mimic-iii")
    errors = _compare(documented, actual)
    assert not errors, "MIMIC-III schema drift:\n" + "\n".join(errors)


@pytest.mark.schema
def test_mimic4_schema_matches_reference():
    ds = DATASETS.get("mimic-iv")
    if not ds or not ds.base_path.exists():
        pytest.skip("MIMIC-IV data not available locally")

    text = SCHEMA_DOC.read_text()
    documented = _parse_section(text, _SECTION_MIMIC4, [_SECTION_MIMIC4_NOTE, _SECTION_MIMIC3])
    actual = _get_actual_columns("mimic-iv")
    errors = _compare(documented, actual)
    assert not errors, "MIMIC-IV schema drift:\n" + "\n".join(errors)


@pytest.mark.schema
def test_mimic4_note_schema_matches_reference():
    ds = DATASETS.get("mimic-iv")
    if not ds or not ds.note_path or not ds.note_path.exists():
        pytest.skip("MIMIC-IV-Note data not available locally")

    text = SCHEMA_DOC.read_text()
    documented = _parse_section(text, _SECTION_MIMIC4_NOTE, [_SECTION_MIMIC3])
    conn = get_connection()
    actual: dict[str, set[str]] = {}
    for name, path in ds.find_note_tables().items():
        cols = column_info(conn, path)
        actual[name] = {c["name"].lower() for c in cols}

    errors = _compare(documented, actual)
    assert not errors, "MIMIC-IV-Note schema drift:\n" + "\n".join(errors)
