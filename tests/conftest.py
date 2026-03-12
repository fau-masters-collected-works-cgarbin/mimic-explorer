"""Shared test fixtures for MIMIC Explorer tests."""

import gzip
from pathlib import Path

import pytest


@pytest.fixture
def sample_csv_gz(tmp_path: Path) -> Path:
    """Create a small CSV.gz file for testing."""
    csv_content = "subject_id,hadm_id,name\n1,100,Alice\n2,200,Bob\n3,300,Charlie\n"
    file_path = tmp_path / "TEST_TABLE.csv.gz"
    with gzip.open(file_path, "wt") as f:
        f.write(csv_content)
    return file_path


@pytest.fixture
def mimic3_layout(tmp_path: Path) -> Path:
    """Create a MIMIC-III-like directory layout with two tables."""
    base = tmp_path / "mimic-iii"
    base.mkdir()

    for name, content in [
        ("ADMISSIONS.csv.gz", "subject_id,hadm_id\n1,100\n2,200\n"),
        ("PATIENTS.csv.gz", "subject_id,gender,dob\n1,M,2000-01-01\n2,F,1990-06-15\n"),
    ]:
        with gzip.open(base / name, "wt") as f:
            f.write(content)

    return base


@pytest.fixture
def mimic4_layout(tmp_path: Path) -> Path:
    """Create a MIMIC-IV-like directory layout with subdirectories."""
    base = tmp_path / "mimic-iv"
    hosp = base / "hosp"
    icu = base / "icu"
    hosp.mkdir(parents=True)
    icu.mkdir(parents=True)

    with gzip.open(hosp / "admissions.csv.gz", "wt") as f:
        f.write("subject_id,hadm_id\n10,1000\n")

    with gzip.open(icu / "icustays.csv.gz", "wt") as f:
        f.write("subject_id,stay_id\n10,5000\n")

    return base
