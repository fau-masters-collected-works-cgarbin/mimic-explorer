"""Tests for timeline data-fetching queries."""

import gzip
from pathlib import Path

import pytest

from mimic_explorer.db import table_ref
from mimic_explorer.timeline_queries import (
    fetch_admission_bounds,
    fetch_admission_data,
    fetch_category_counts,
    fetch_note_text,
    fetch_random_hadm_ids,
)


@pytest.fixture
def noteevents_csv_gz(tmp_path: Path) -> Path:
    """Noteevents table with mixed timestamps, error flags, and multiple admissions."""
    csv = (
        "ROW_ID,SUBJECT_ID,HADM_ID,CATEGORY,DESCRIPTION,CHARTTIME,CHARTDATE,TEXT,ISERROR\n"
        # hadm 100: three notes, one with chartdate only, one error
        '1,10,100,Nursing,Progress,"2150-01-01 08:00:00","2150-01-01",Note one,\n'
        '2,10,100,Physician,Attending,"2150-01-01 14:00:00","2150-01-01",Note two,\n'
        '3,10,100,Nursing,Progress,,"2150-01-02",Date-only note,\n'
        '4,10,100,Nursing,Error note,"2150-01-01 10:00:00","2150-01-01",Error text,1\n'
        # hadm 200: one note (below threshold for random selection)
        '5,20,200,Discharge,Summary,"2150-02-01 12:00:00","2150-02-01",Discharge note,\n'
        # hadm 300: three notes (eligible for random selection)
        '6,30,300,Nursing,Progress,"2150-03-01 08:00:00","2150-03-01",Note A,\n'
        '7,30,300,Physician,Attending,"2150-03-01 12:00:00","2150-03-01",Note B,\n'
        '8,30,300,Nursing,Progress,"2150-03-02 09:00:00","2150-03-02",Note C,\n'
    )
    path = tmp_path / "NOTEEVENTS.csv.gz"
    with gzip.open(path, "wt") as f:
        f.write(csv)
    return path


@pytest.fixture
def labevents_csv_gz(tmp_path: Path) -> Path:
    """Lab events with flagged and unflagged results."""
    csv = (
        "ROW_ID,SUBJECT_ID,HADM_ID,ITEMID,CHARTTIME,VALUE,VALUEUOM,FLAG\n"
        '1,10,100,50811,"2150-01-01 09:00:00",7.2,mg/dL,abnormal\n'
        '2,10,100,50813,"2150-01-01 10:00:00",140,mEq/L,\n'  # not flagged
        '3,10,100,50818,"2150-01-01 11:00:00",3.5,mEq/L,abnormal\n'
        "4,10,100,50820,,4.0,mEq/L,abnormal\n"  # null charttime
    )
    path = tmp_path / "LABEVENTS.csv.gz"
    with gzip.open(path, "wt") as f:
        f.write(csv)
    return path


@pytest.fixture
def transfers_csv_gz(tmp_path: Path) -> Path:
    csv = (
        "ROW_ID,SUBJECT_ID,HADM_ID,EVENTTYPE,CURR_CAREUNIT,INTIME\n"
        '1,10,100,admit,MICU,"2150-01-01 07:00:00"\n'
        '2,10,100,transfer,SICU,"2150-01-01 18:00:00"\n'
        "3,10,100,discharge,,\n"  # null intime
    )
    path = tmp_path / "TRANSFERS.csv.gz"
    with gzip.open(path, "wt") as f:
        f.write(csv)
    return path


@pytest.fixture
def prescriptions_csv_gz(tmp_path: Path) -> Path:
    csv = (
        "ROW_ID,SUBJECT_ID,HADM_ID,STARTDATE,ENDDATE,DRUG\n"
        '1,10,100,"2150-01-01","2150-01-03",Vancomycin\n'
        '2,10,100,"2150-01-02","2150-01-04",Metoprolol\n'
    )
    path = tmp_path / "PRESCRIPTIONS.csv.gz"
    with gzip.open(path, "wt") as f:
        f.write(csv)
    return path


def _note_ref(path: Path) -> str:
    return f"read_csv_auto('{path}')"


# -- fetch_category_counts --


def test_category_counts_without_error_filter(noteevents_csv_gz):
    df = fetch_category_counts(_note_ref(noteevents_csv_gz), "CATEGORY", None)
    counts = dict(zip(df["category"], df["count"], strict=True))
    # All 8 rows counted (including the error note)
    assert counts["Nursing"] == 5
    assert counts["Physician"] == 2
    assert counts["Discharge"] == 1


def test_category_counts_with_error_filter(noteevents_csv_gz):
    error_filter = '("ISERROR" != \'1\' OR "ISERROR" IS NULL)'
    df = fetch_category_counts(_note_ref(noteevents_csv_gz), "CATEGORY", error_filter)
    counts = dict(zip(df["category"], df["count"], strict=True))
    # Error note excluded: Nursing drops from 5 to 4
    assert counts["Nursing"] == 4


# -- fetch_random_hadm_ids --


def test_random_hadm_ids_filters_by_note_count(noteevents_csv_gz):
    ids = fetch_random_hadm_ids(_note_ref(noteevents_csv_gz), "HADM_ID", None)
    # hadm 100 has 4 notes, hadm 300 has 3 -> both eligible (>= 3)
    # hadm 200 has 1 note -> excluded
    assert 200 not in ids
    assert set(ids).issubset({100, 300})


def test_random_hadm_ids_with_error_filter(noteevents_csv_gz):
    error_filter = '("ISERROR" != \'1\' OR "ISERROR" IS NULL)'
    ids = fetch_random_hadm_ids(_note_ref(noteevents_csv_gz), "HADM_ID", error_filter)
    # hadm 100: 4 notes minus 1 error = 3 -> still eligible
    # hadm 300: 3 notes -> eligible
    assert set(ids).issubset({100, 300})


# -- fetch_note_text --


def test_fetch_note_text_by_id(noteevents_csv_gz):
    text = fetch_note_text(_note_ref(noteevents_csv_gz), "1", "TEXT", "ROW_ID")
    assert text == "Note one"


def test_fetch_note_text_missing_id(noteevents_csv_gz):
    text = fetch_note_text(_note_ref(noteevents_csv_gz), "999", "TEXT", "ROW_ID")
    assert text is None


# -- fetch_admission_data (parallel fetch) --


class TestFetchAdmissionData:
    """Tests for the parallel admission data fetcher."""

    @staticmethod
    def _note_cols(*, with_chartdate: bool, with_error_filter: bool):
        return {
            "row_id_col": "ROW_ID",
            "category_col": "CATEGORY",
            "description_col": "DESCRIPTION",
            "charttime_col": "CHARTTIME",
            "chartdate_col": "CHARTDATE" if with_chartdate else None,
            "hadm_col": "HADM_ID",
            "error_filter": (
                '("ISERROR" != \'1\' OR "ISERROR" IS NULL)' if with_error_filter else None
            ),
        }

    @staticmethod
    def _lab_cols():
        return {
            "charttime": "CHARTTIME",
            "flag": "FLAG",
            "itemid": "ITEMID",
            "hadm": "HADM_ID",
            "value": "VALUE",
            "valueuom": "VALUEUOM",
        }

    @staticmethod
    def _xfer_cols():
        return {
            "intime": "INTIME",
            "eventtype": "EVENTTYPE",
            "careunit": "CURR_CAREUNIT",
            "hadm": "HADM_ID",
        }

    @staticmethod
    def _rx_cols():
        return {
            "starttime": "STARTDATE",
            "stoptime": "ENDDATE",
            "drug": "DRUG",
            "hadm": "HADM_ID",
        }

    def test_notes_with_chartdate_and_error_filter(
        self, noteevents_csv_gz, labevents_csv_gz, transfers_csv_gz, prescriptions_csv_gz
    ):
        data = fetch_admission_data(
            100,
            _note_ref(noteevents_csv_gz),
            _note_ref(labevents_csv_gz),
            _note_ref(transfers_csv_gz),
            _note_ref(prescriptions_csv_gz),
            note_cols=self._note_cols(with_chartdate=True, with_error_filter=True),
            lab_cols=self._lab_cols(),
            xfer_cols=self._xfer_cols(),
            rx_cols=self._rx_cols(),
        )
        assert set(data.keys()) == {"notes", "labs", "transfers", "meds"}

        # Notes: 4 rows for hadm 100, minus 1 error = 3
        assert len(data["notes"]) == 3
        # The date-only note (ROW_ID 3) should be included
        assert 3 in data["notes"]["ROW_ID"].values

    def test_notes_without_chartdate(
        self, noteevents_csv_gz, labevents_csv_gz, transfers_csv_gz, prescriptions_csv_gz
    ):
        data = fetch_admission_data(
            100,
            _note_ref(noteevents_csv_gz),
            _note_ref(labevents_csv_gz),
            _note_ref(transfers_csv_gz),
            _note_ref(prescriptions_csv_gz),
            note_cols=self._note_cols(with_chartdate=False, with_error_filter=False),
            lab_cols=self._lab_cols(),
            xfer_cols=self._xfer_cols(),
            rx_cols=self._rx_cols(),
        )
        # Without error filter: all 4 notes for hadm 100
        assert len(data["notes"]) == 4

    def test_abnormal_labs_filtered(
        self, noteevents_csv_gz, labevents_csv_gz, transfers_csv_gz, prescriptions_csv_gz
    ):
        data = fetch_admission_data(
            100,
            _note_ref(noteevents_csv_gz),
            _note_ref(labevents_csv_gz),
            _note_ref(transfers_csv_gz),
            _note_ref(prescriptions_csv_gz),
            note_cols=self._note_cols(with_chartdate=True, with_error_filter=False),
            lab_cols=self._lab_cols(),
            xfer_cols=self._xfer_cols(),
            rx_cols=self._rx_cols(),
        )
        labs = data["labs"]
        # 2 abnormal with non-null charttime (row 1 and 3; row 2 not flagged, row 4 null charttime)
        assert len(labs) == 2
        assert all(labs["flag"] == "abnormal")

    def test_transfers_filtered(
        self, noteevents_csv_gz, labevents_csv_gz, transfers_csv_gz, prescriptions_csv_gz
    ):
        data = fetch_admission_data(
            100,
            _note_ref(noteevents_csv_gz),
            _note_ref(labevents_csv_gz),
            _note_ref(transfers_csv_gz),
            _note_ref(prescriptions_csv_gz),
            note_cols=self._note_cols(with_chartdate=True, with_error_filter=False),
            lab_cols=self._lab_cols(),
            xfer_cols=self._xfer_cols(),
            rx_cols=self._rx_cols(),
        )
        xfers = data["transfers"]
        # 2 transfers with non-null intime (row 3 has null intime)
        assert len(xfers) == 2
        assert set(xfers["careunit"]) == {"MICU", "SICU"}

    def test_medications(
        self, noteevents_csv_gz, labevents_csv_gz, transfers_csv_gz, prescriptions_csv_gz
    ):
        data = fetch_admission_data(
            100,
            _note_ref(noteevents_csv_gz),
            _note_ref(labevents_csv_gz),
            _note_ref(transfers_csv_gz),
            _note_ref(prescriptions_csv_gz),
            note_cols=self._note_cols(with_chartdate=True, with_error_filter=False),
            lab_cols=self._lab_cols(),
            xfer_cols=self._xfer_cols(),
            rx_cols=self._rx_cols(),
        )
        meds = data["meds"]
        assert len(meds) == 2
        assert set(meds["drug"]) == {"Vancomycin", "Metoprolol"}

    def test_none_refs_return_empty_dataframes(self, noteevents_csv_gz):
        data = fetch_admission_data(
            100,
            _note_ref(noteevents_csv_gz),
            None,
            None,
            None,
            note_cols=self._note_cols(with_chartdate=True, with_error_filter=False),
            lab_cols=self._lab_cols(),
            xfer_cols=self._xfer_cols(),
            rx_cols=self._rx_cols(),
        )
        assert data["labs"].empty
        assert data["transfers"].empty
        assert data["meds"].empty
        # Notes still returned
        assert not data["notes"].empty


# -- fetch_admission_bounds --


@pytest.fixture
def admissions_csv_gz(tmp_path: Path) -> Path:
    csv = (
        "ROW_ID,SUBJECT_ID,HADM_ID,ADMITTIME,DISCHTIME\n"
        "1,10,100,2150-01-01 08:00:00,2150-01-05 14:00:00\n"
        "2,20,200,2150-02-10 12:00:00,2150-02-12 09:00:00\n"
    )
    path = tmp_path / "ADMISSIONS.csv.gz"
    with gzip.open(path, "wt") as f:
        f.write(csv)
    return path


def test_fetch_admission_bounds(admissions_csv_gz):
    result = fetch_admission_bounds(
        table_ref(admissions_csv_gz), 100, "HADM_ID", "ADMITTIME", "DISCHTIME"
    )
    assert result is not None
    assert str(result["admit"]) == "2150-01-01 08:00:00"
    assert str(result["disch"]) == "2150-01-05 14:00:00"


def test_fetch_admission_bounds_missing_hadm(admissions_csv_gz):
    result = fetch_admission_bounds(
        table_ref(admissions_csv_gz), 999, "HADM_ID", "ADMITTIME", "DISCHTIME"
    )
    assert result is None
