"""Tests for the DuckDB connection and query helpers."""

from pathlib import Path

from mimic_explorer.db import column_info, get_connection, row_count, sample_rows, table_ref


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
    df = result.fetchdf()
    assert len(df) == 2
    assert "subject_id" in df.columns


def test_sample_rows_respects_limit(sample_csv_gz):
    conn = get_connection()
    result = sample_rows(conn, sample_csv_gz, limit=1)
    df = result.fetchdf()
    assert len(df) == 1
