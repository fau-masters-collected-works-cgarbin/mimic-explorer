"""Tests for the DuckDB connection and query helpers."""

from pathlib import Path

from mimic_explorer.db import (
    column_info,
    get_connection,
    note_union_ref,
    resolve_refs,
    row_count,
    sample_rows,
    scalar_query,
    table_ref,
)


def test_table_ref_produces_valid_sql():
    ref = table_ref(Path("/some/path/TABLE.csv.gz"))
    assert "read_csv_auto" in ref
    assert "TABLE.csv.gz" in ref


def test_row_count(sample_csv_gz):
    conn = get_connection()
    assert row_count(conn, sample_csv_gz) == 3


def test_column_info(sample_csv_gz):
    conn = get_connection()
    cols = column_info(conn, sample_csv_gz)
    names = [c["name"] for c in cols]
    assert "subject_id" in names
    assert "hadm_id" in names
    assert "name" in names
    assert len(cols) == 3
    # Each entry has name and type
    for c in cols:
        assert "name" in c
        assert "type" in c


def test_sample_rows(sample_csv_gz):
    conn = get_connection()
    result = sample_rows(conn, sample_csv_gz, limit=2)
    assert len(result) == 2
    assert "subject_id" in result.columns


def test_sample_rows_respects_limit(sample_csv_gz):
    conn = get_connection()
    result = sample_rows(conn, sample_csv_gz, limit=1)
    assert len(result) == 1


def test_scalar_query(sample_csv_gz):
    conn = get_connection()
    ref = table_ref(sample_csv_gz)
    result = scalar_query(conn, f"SELECT count(*) FROM {ref}")
    assert result == 3


def test_scalar_query_with_aggregate(sample_csv_gz):
    conn = get_connection()
    ref = table_ref(sample_csv_gz)
    result = scalar_query(conn, f"SELECT max(subject_id) FROM {ref}")
    assert result == 3


def test_resolve_refs(sample_csv_gz):
    tables = {"test_table": sample_csv_gz}
    refs = resolve_refs(tables, ["test_table", "missing_table"])
    assert "read_csv_auto" in refs["test_table"]
    assert refs["missing_table"] is None


def test_note_union_ref_returns_none_for_empty():
    assert note_union_ref({}) is None


def test_note_union_ref_query(mimic4_note_layout):
    from mimic_explorer.config import DatasetConfig  # noqa: PLC0415

    config = DatasetConfig(name="test", base_path=mimic4_note_layout, note_path=mimic4_note_layout)
    note_tables = config.find_note_tables()
    ref = note_union_ref(note_tables)
    assert ref is not None

    conn = get_connection()
    result = conn.execute(f"SELECT * FROM {ref}").fetchdf()
    assert len(result) == 3
    assert "category" in result.columns
    categories = set(result["category"])
    assert "Discharge summary" in categories
    assert "Radiology" in categories
