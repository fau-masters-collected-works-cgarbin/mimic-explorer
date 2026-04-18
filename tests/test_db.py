"""Tests for the DuckDB connection and query helpers."""

from pathlib import Path

from mimic_explorer.config import DatasetConfig
from mimic_explorer.db import (
    column_info,
    get_connection,
    note_union_ref,
    resolve_note_ref,
    resolve_refs,
    row_count,
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


def test_resolve_note_ref_mimic3_with_noteevents(mimic3_layout):
    import gzip  # noqa: PLC0415

    noteevents = (
        "ROW_ID,SUBJECT_ID,HADM_ID,CHARTTIME,CATEGORY,TEXT\n"
        "1,1,100,2150-01-01 12:00:00,Discharge summary,note text\n"
    )
    with gzip.open(mimic3_layout / "NOTEEVENTS.csv.gz", "wt") as f:
        f.write(noteevents)

    cfg = DatasetConfig(name="m3", base_path=mimic3_layout, uppercase_filenames=True)
    ref = resolve_note_ref(cfg)
    assert ref is not None
    assert "NOTEEVENTS.csv.gz" in ref
    assert "read_csv_auto" in ref


def test_resolve_note_ref_mimic3_without_noteevents(mimic3_layout):
    cfg = DatasetConfig(name="m3", base_path=mimic3_layout, uppercase_filenames=True)
    assert resolve_note_ref(cfg) is None


def test_resolve_note_ref_mimic4_with_note_module(mimic4_layout, mimic4_note_layout):
    cfg = DatasetConfig(
        name="m4",
        base_path=mimic4_layout,
        subdirs=("hosp", "icu"),
        note_path=mimic4_note_layout,
    )
    ref = resolve_note_ref(cfg)
    assert ref is not None

    conn = get_connection()
    result = conn.execute(f"SELECT category, COUNT(*) AS n FROM {ref} GROUP BY category").fetchdf()
    assert set(result["category"]) == {"Discharge summary", "Radiology"}


def test_resolve_note_ref_mimic4_without_note_module(mimic4_layout):
    cfg = DatasetConfig(name="m4", base_path=mimic4_layout, subdirs=("hosp", "icu"))
    assert resolve_note_ref(cfg) is None


def test_resolve_note_ref_mimic4_empty_note_path(mimic4_layout, tmp_path):
    empty_note_dir = tmp_path / "empty-notes"
    empty_note_dir.mkdir()
    cfg = DatasetConfig(
        name="m4",
        base_path=mimic4_layout,
        subdirs=("hosp", "icu"),
        note_path=empty_note_dir,
    )
    assert resolve_note_ref(cfg) is None
