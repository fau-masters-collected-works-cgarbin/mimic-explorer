"""Tests for dataset configuration and table discovery."""

from pathlib import Path

from mimic_explorer.config import DatasetConfig


def test_find_tables_flat_directory(mimic3_layout):
    config = DatasetConfig(
        name="MIMIC-III test",
        base_path=mimic3_layout,
        uppercase_filenames=True,
    )
    tables = config.find_tables()
    assert "admissions" in tables
    assert "patients" in tables
    assert len(tables) == 2
    # Paths should point to actual files
    for path in tables.values():
        assert path.exists()


def test_find_tables_subdirectories(mimic4_layout):
    config = DatasetConfig(
        name="MIMIC-IV test",
        base_path=mimic4_layout,
        subdirs=("hosp", "icu"),
    )
    tables = config.find_tables()
    assert "admissions" in tables
    assert "icustays" in tables
    assert len(tables) == 2


def test_find_tables_empty_directory(tmp_path):
    config = DatasetConfig(name="empty", base_path=tmp_path)
    tables = config.find_tables()
    assert tables == {}


def test_find_tables_nonexistent_subdir(tmp_path):
    config = DatasetConfig(
        name="missing",
        base_path=tmp_path,
        subdirs=("nonexistent",),
    )
    tables = config.find_tables()
    assert tables == {}


def test_find_note_tables_returns_tables(mimic4_note_layout):
    config = DatasetConfig(
        name="MIMIC-IV test",
        base_path=mimic4_note_layout,  # not used by find_note_tables
        note_path=mimic4_note_layout,
    )
    note_tables = config.find_note_tables()
    assert "discharge" in note_tables
    assert "radiology" in note_tables
    assert "discharge_detail" in note_tables  # discovery returns all csv.gz files
    for path in note_tables.values():
        assert path.exists()


def test_find_note_tables_none_path():
    config = DatasetConfig(name="no notes", base_path=Path("/fake"), note_path=None)
    assert config.find_note_tables() == {}


def test_find_note_tables_nonexistent_path(tmp_path):
    config = DatasetConfig(
        name="missing notes",
        base_path=tmp_path,
        note_path=tmp_path / "nonexistent",
    )
    assert config.find_note_tables() == {}


def test_col_mimic3():
    config = DatasetConfig(name="MIMIC-III test", base_path=Path("/fake"), uppercase_filenames=True)
    assert config.col("gender") == "GENDER"
    assert config.col("race") == "ETHNICITY"
    assert config.col("icu_key") == "icustay_id"
    assert config.col("iserror") == "ISERROR"
    assert config.col("chartdate") == "CHARTDATE"
    assert config.col("careunit") == "CURR_CAREUNIT"
    assert config.col("nonexistent") is None


def test_col_mimic4():
    config = DatasetConfig(name="MIMIC-IV test", base_path=Path("/fake"))
    assert config.col("gender") == "gender"
    assert config.col("race") == "race"
    assert config.col("icu_key") == "stay_id"
    assert config.col("iserror") is None
    assert config.col("chartdate") is None
    assert config.col("careunit") == "careunit"
    assert config.col("nonexistent") is None
