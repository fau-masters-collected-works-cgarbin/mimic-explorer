"""Tests for dataset configuration and table discovery."""

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
