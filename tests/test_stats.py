"""Tests for the stats module (pre-computed dataset statistics)."""

import gzip
import json
from pathlib import Path

import numpy as np
import pytest

from mimic_explorer.config import DatasetConfig
from mimic_explorer.stats import (
    _NumpyEncoder,
    compute_stats,
    load_stats,
    save_stats,
)


@pytest.fixture
def mimic3_dataset(tmp_path: Path) -> DatasetConfig:
    """Create a MIMIC-III-like dataset with enough tables for stats queries."""
    base = tmp_path / "mimic-iii"
    base.mkdir()

    patients = (
        "ROW_ID,SUBJECT_ID,GENDER,DOB\n1,1,M,2050-01-01\n2,2,F,2060-06-15\n3,3,M,2055-03-20\n"
    )
    admissions = (
        "ROW_ID,SUBJECT_ID,HADM_ID,ADMITTIME,DISCHTIME,HOSPITAL_EXPIRE_FLAG,ETHNICITY\n"
        "1,1,100,2100-01-01 08:00:00,2100-01-05 14:00:00,0,WHITE\n"
        "2,2,200,2100-02-10 12:00:00,2100-02-12 09:00:00,1,BLACK\n"
        "3,3,300,2100-03-15 06:00:00,2100-03-20 18:00:00,0,WHITE\n"
        "4,1,400,2100-06-01 10:00:00,2100-06-03 16:00:00,0,WHITE\n"
    )
    icustays = "ROW_ID,SUBJECT_ID,HADM_ID,ICUSTAY_ID,LOS\n1,1,100,1001,2.5\n2,2,200,1002,1.0\n"
    diagnoses = (
        "ROW_ID,SUBJECT_ID,HADM_ID,SEQ_NUM,ICD9_CODE\n"
        "1,1,100,1,4019\n"
        "2,2,200,1,4019\n"
        "3,3,300,1,25000\n"
    )
    d_icd_diagnoses = (
        "ROW_ID,ICD9_CODE,SHORT_TITLE,LONG_TITLE\n"
        '1,4019,Hypertension NOS,"Unspecified essential hypertension"\n'
        '2,25000,Diabetes mellitus,"Diabetes mellitus without mention of complication"\n'
    )
    procedures = "ROW_ID,SUBJECT_ID,HADM_ID,SEQ_NUM,ICD9_CODE\n1,1,100,1,3893\n2,2,200,1,3893\n"
    d_icd_procedures = (
        "ROW_ID,ICD9_CODE,SHORT_TITLE,LONG_TITLE\n"
        '1,3893,Venous cath NEC,"Venous catheterization, not elsewhere classified"\n'
    )
    labevents = (
        "ROW_ID,SUBJECT_ID,HADM_ID,ITEMID,CHARTTIME,VALUE,VALUENUM,VALUEUOM,FLAG\n"
        "1,1,100,50811,2100-01-02 06:00:00,12.5,12.5,g/dL,\n"
        "2,1,100,50811,2100-01-03 06:00:00,11.0,11.0,g/dL,\n"
        "3,2,200,50912,2100-02-11 08:00:00,1.2,1.2,mg/dL,\n"
        "4,3,300,50811,,13.0,13.0,g/dL,\n"
    )
    d_labitems = (
        "ROW_ID,ITEMID,LABEL,FLUID,CATEGORY,LOINC_CODE\n"
        "1,50811,Hemoglobin,Blood,Hematology,718-7\n"
        "2,50912,Creatinine,Blood,Chemistry,2160-0\n"
    )
    prescriptions = (
        "ROW_ID,SUBJECT_ID,HADM_ID,STARTDATE,ENDDATE,DRUG\n"
        "1,1,100,2100-01-01,2100-01-05,Aspirin\n"
        "2,2,200,2100-02-10,2100-02-12,Metformin\n"
    )
    transfers = (
        "ROW_ID,SUBJECT_ID,HADM_ID,EVENTTYPE,CURR_CAREUNIT,INTIME,OUTTIME\n"
        "1,1,100,admit,MICU,2100-01-01 08:00:00,2100-01-03 10:00:00\n"
        "2,2,200,admit,SICU,2100-02-10 12:00:00,2100-02-11 14:00:00\n"
    )
    noteevents = (
        "ROW_ID,SUBJECT_ID,HADM_ID,CHARTDATE,CHARTTIME,CATEGORY,DESCRIPTION,ISERROR,TEXT\n"
        "1,1,100,2100-01-02,2100-01-02 10:00:00,Nursing,Nursing note,,Note text here\n"
        "2,2,200,2100-02-11,,Discharge summary,Report,,\n"
        '3,3,300,2100-03-16,2100-03-16 14:00:00,Radiology,Chest X-ray,,""\n'
    )

    for name, content in [
        ("PATIENTS.csv.gz", patients),
        ("ADMISSIONS.csv.gz", admissions),
        ("ICUSTAYS.csv.gz", icustays),
        ("DIAGNOSES_ICD.csv.gz", diagnoses),
        ("D_ICD_DIAGNOSES.csv.gz", d_icd_diagnoses),
        ("PROCEDURES_ICD.csv.gz", procedures),
        ("D_ICD_PROCEDURES.csv.gz", d_icd_procedures),
        ("LABEVENTS.csv.gz", labevents),
        ("D_LABITEMS.csv.gz", d_labitems),
        ("PRESCRIPTIONS.csv.gz", prescriptions),
        ("TRANSFERS.csv.gz", transfers),
        ("NOTEEVENTS.csv.gz", noteevents),
    ]:
        with gzip.open(base / name, "wt") as f:
            f.write(content)

    return DatasetConfig(name="Test MIMIC-III", base_path=base, uppercase_filenames=True)


class TestCacheIO:
    def test_load_returns_none_when_no_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mimic_explorer.stats.CACHE_DIR", tmp_path)
        assert load_stats("nonexistent") is None

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mimic_explorer.stats.CACHE_DIR", tmp_path)
        data = {"overview": {"total_patients": 100}, "top_diagnoses": [{"d": "Flu", "count": 5}]}
        save_stats("test-dataset", data)
        loaded = load_stats("test-dataset")
        assert loaded == data

    def test_numpy_encoder_handles_numpy_types(self):
        data = {
            "int": np.int64(42),
            "float": np.float64(3.14),
            "array": np.array([1, 2, 3]),
        }
        result = json.loads(json.dumps(data, cls=_NumpyEncoder))
        assert result["int"] == 42
        assert isinstance(result["int"], int)
        assert result["float"] == pytest.approx(3.14)
        assert result["array"] == [1, 2, 3]

    def test_save_handles_numpy_types(self, tmp_path, monkeypatch):
        monkeypatch.setattr("mimic_explorer.stats.CACHE_DIR", tmp_path)
        data = {"overview": {"total_patients": np.int64(100), "rate": np.float64(0.5)}}
        save_stats("test-numpy", data)
        loaded = load_stats("test-numpy")
        assert loaded["overview"]["total_patients"] == 100
        assert isinstance(loaded["overview"]["total_patients"], int)


class TestComputeStats:
    def test_overview_metrics(self, mimic3_dataset):
        result = compute_stats(mimic3_dataset)
        overview = result["overview"]
        assert overview["total_patients"] == 3
        assert overview["total_admissions"] == 4
        assert overview["total_icu_stays"] == 2
        assert overview["male_pct"] is not None
        assert overview["mortality_pct"] is not None
        assert overview["median_los"] is not None

    def test_top_diagnoses(self, mimic3_dataset):
        result = compute_stats(mimic3_dataset)
        assert "top_diagnoses" in result
        diags = result["top_diagnoses"]
        assert len(diags) > 0
        assert "diagnosis" in diags[0]
        assert "count" in diags[0]
        # Hypertension appears twice, diabetes once
        hyp = next(d for d in diags if "hypertension" in d["diagnosis"].lower())
        assert hyp["count"] == 2

    def test_top_procedures(self, mimic3_dataset):
        result = compute_stats(mimic3_dataset)
        assert "top_procedures" in result
        procs = result["top_procedures"]
        assert len(procs) > 0
        assert "procedure" in procs[0]

    def test_top_labs(self, mimic3_dataset):
        result = compute_stats(mimic3_dataset)
        assert "top_labs" in result
        labs = result["top_labs"]
        assert len(labs) > 0
        hgb = next(row for row in labs if "Hemoglobin" in row["lab_test"])
        assert hgb["count"] == 3

    def test_gender_distribution(self, mimic3_dataset):
        result = compute_stats(mimic3_dataset)
        assert "gender_dist" in result
        genders = {g["gender"]: g["count"] for g in result["gender_dist"]}
        assert genders["M"] == 2
        assert genders["F"] == 1

    def test_race_distribution(self, mimic3_dataset):
        result = compute_stats(mimic3_dataset)
        assert "race_dist" in result
        races = {r["race"]: r["count"] for r in result["race_dist"]}
        assert races["WHITE"] == 3
        assert races["BLACK"] == 1

    def test_age_distribution(self, mimic3_dataset):
        result = compute_stats(mimic3_dataset)
        assert "age_dist" in result
        assert len(result["age_dist"]) > 0
        assert "age" in result["age_dist"][0]

    def test_los_distribution(self, mimic3_dataset):
        result = compute_stats(mimic3_dataset)
        assert "los_dist" in result
        assert len(result["los_dist"]) > 0
        assert "los_days" in result["los_dist"][0]

    def test_per_admission_volume(self, mimic3_dataset):
        result = compute_stats(mimic3_dataset)
        assert "per_admission_volume" in result
        vol = result["per_admission_volume"]
        assert "Notes" in vol
        assert "Labs" in vol
        for stats in vol.values():
            assert "median" in stats
            assert "p25" in stats
            assert "p75" in stats
            assert "max" in stats

    def test_table_coverage(self, mimic3_dataset):
        result = compute_stats(mimic3_dataset)
        assert "table_coverage" in result
        coverage = result["table_coverage"]
        # 3 of 4 admissions have at least one diagnosis
        assert coverage["diagnoses_icd"] == pytest.approx(75.0)
        # prescriptions: 2 of 4 admissions
        assert coverage["prescriptions"] == pytest.approx(50.0)
        assert "labevents" in coverage
        assert "transfers" in coverage
        # Notes are reported under a unified "notes" label for both versions,
        # not under the version-specific table name (e.g. "noteevents").
        assert "notes" in coverage
        assert "noteevents" not in coverage

    def test_data_quality(self, mimic3_dataset):
        result = compute_stats(mimic3_dataset)
        assert "data_quality" in result
        checks = {c["check"]: c for c in result["data_quality"]}
        # One note has missing CHARTTIME (ROW_ID=2)
        assert checks["Notes with missing timestamps"]["count"] == 1
        # Two notes have empty text: ROW_ID=2 (NULL) and ROW_ID=3 ("")
        assert checks["Empty notes"]["count"] == 2
        # One lab has missing CHARTTIME (ROW_ID=4)
        assert checks["Labs with missing timestamps"]["count"] == 1

    def test_full_roundtrip_through_json(self, mimic3_dataset, tmp_path, monkeypatch):
        """Verify compute -> save -> load produces valid, typed data."""
        monkeypatch.setattr("mimic_explorer.stats.CACHE_DIR", tmp_path)
        result = compute_stats(mimic3_dataset)
        save_stats("test-roundtrip", result)
        loaded = load_stats("test-roundtrip")

        # Scalar values should be native Python types after roundtrip
        assert isinstance(loaded["overview"]["total_patients"], int)
        assert isinstance(loaded["overview"]["male_pct"], float)

        # List-of-dict values should have numeric counts
        for diag in loaded["top_diagnoses"]:
            assert isinstance(diag["count"], int)

    def test_missing_tables_still_produce_partial_results(self, tmp_path):
        """Stats should gracefully handle datasets with only patients + admissions."""
        base = tmp_path / "minimal"
        base.mkdir()
        patients = "ROW_ID,SUBJECT_ID,GENDER,DOB\n1,1,M,2050-01-01\n"
        admissions = (
            "ROW_ID,SUBJECT_ID,HADM_ID,ADMITTIME,DISCHTIME,"
            "HOSPITAL_EXPIRE_FLAG,ETHNICITY\n"
            "1,1,100,2100-01-01 08:00:00,2100-01-05 14:00:00,0,WHITE\n"
        )
        for name, content in [
            ("PATIENTS.csv.gz", patients),
            ("ADMISSIONS.csv.gz", admissions),
        ]:
            with gzip.open(base / name, "wt") as f:
                f.write(content)

        cfg = DatasetConfig(name="Minimal", base_path=base, uppercase_filenames=True)
        result = compute_stats(cfg)
        assert result["overview"]["total_patients"] == 1
        # No diagnoses table, so key should be absent
        assert "top_diagnoses" not in result
