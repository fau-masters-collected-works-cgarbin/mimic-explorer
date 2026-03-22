"""Dataset path configuration for MIMIC-III and MIMIC-IV."""

import os
from dataclasses import dataclass
from pathlib import Path

# Column name mappings: logical name to actual column name per MIMIC version.
# Logical names are lowercase. None means the column doesn't exist in that version.
# Most differences are just casing, but some columns have genuinely different names:
#   MIMIC-III ETHNICITY -> MIMIC-IV race
#   MIMIC-III icustay_id -> MIMIC-IV stay_id
#   MIMIC-III CURR_CAREUNIT -> MIMIC-IV careunit
#   MIMIC-III STARTDATE/ENDDATE -> MIMIC-IV starttime/stoptime
#   MIMIC-III ROW_ID -> MIMIC-IV note_id
#   MIMIC-III DESCRIPTION -> MIMIC-IV note_type
#   MIMIC-III ISERROR/CHARTDATE -> no MIMIC-IV equivalent
_COLUMNS_MIMIC3: dict[str, str | None] = {
    # Identifiers
    "subject_id": "SUBJECT_ID",
    "hadm_id": "HADM_ID",
    "icu_key": "icustay_id",
    # Patient demographics
    "gender": "GENDER",
    "race": "ETHNICITY",
    # Admissions
    "admittime": "ADMITTIME",
    "dischtime": "DISCHTIME",
    "hospital_expire_flag": "HOSPITAL_EXPIRE_FLAG",
    # ICU stays
    "los": "LOS",
    # Diagnoses / procedures
    "icd_code": "ICD9_CODE",
    "long_title": "LONG_TITLE",
    # Labs
    "itemid": "ITEMID",
    "label": "LABEL",
    "charttime": "CHARTTIME",
    "flag": "FLAG",
    "value": "VALUE",
    "valueuom": "VALUEUOM",
    # Notes
    "category": "CATEGORY",
    "chartdate": "CHARTDATE",
    "note_id": "ROW_ID",
    "iserror": "ISERROR",
    "note_type": "DESCRIPTION",
    "text": "TEXT",
    # Transfers
    "intime": "INTIME",
    "eventtype": "EVENTTYPE",
    "careunit": "CURR_CAREUNIT",
    # Prescriptions
    "rx_starttime": "STARTDATE",
    "rx_stoptime": "ENDDATE",
    "drug": "DRUG",
}

_COLUMNS_MIMIC4: dict[str, str | None] = {
    "subject_id": "subject_id",
    "hadm_id": "hadm_id",
    "icu_key": "stay_id",
    "gender": "gender",
    "race": "race",
    "admittime": "admittime",
    "dischtime": "dischtime",
    "hospital_expire_flag": "hospital_expire_flag",
    "los": "los",
    "icd_code": "icd_code",
    "long_title": "long_title",
    "itemid": "itemid",
    "label": "label",
    "charttime": "charttime",
    "flag": "flag",
    "value": "value",
    "valueuom": "valueuom",
    "category": "category",
    "chartdate": None,
    "note_id": "note_id",
    "iserror": None,
    "note_type": "note_type",
    "text": "text",
    "intime": "intime",
    "eventtype": "eventtype",
    "careunit": "careunit",
    "rx_starttime": "starttime",
    "rx_stoptime": "stoptime",
    "drug": "drug",
}


@dataclass(frozen=True)
class DatasetConfig:
    """Configuration for a single MIMIC dataset."""

    name: str
    base_path: Path
    # MIMIC-III: flat directory with UPPERCASE filenames
    # MIMIC-IV: subdirectories (hosp/, icu/) with lowercase filenames
    subdirs: tuple[str, ...] = ()
    uppercase_filenames: bool = False
    # Separate path for MIMIC-IV-Note module (discharge + radiology tables)
    note_path: Path | None = None

    def col(self, name: str) -> str | None:
        """Map a logical column name to the actual column name for this dataset.

        Returns None if the column doesn't exist in this version (e.g. MIMIC-III
        has ISERROR and CHARTDATE on notes, MIMIC-IV does not).
        """
        # uppercase_filenames is a reliable proxy for MIMIC version: III uses
        # UPPERCASE.csv.gz, IV uses lowercase.csv.gz
        mapping = _COLUMNS_MIMIC3 if self.uppercase_filenames else _COLUMNS_MIMIC4
        return mapping.get(name)

    def find_tables(self) -> dict[str, Path]:
        """Discover all CSV.gz tables in this dataset.

        Returns a dict mapping table name (lowercase) to file path.
        """
        tables: dict[str, Path] = {}
        if self.subdirs:
            for subdir in self.subdirs:
                subdir_path = self.base_path / subdir
                if subdir_path.exists():
                    for f in sorted(subdir_path.glob("*.csv.gz")):
                        # Can't use .stem here: it only strips .gz, leaving "TABLE.csv"
                        name = f.name.removesuffix(".csv.gz").lower()
                        tables[name] = f
        else:
            for f in sorted(self.base_path.glob("*.csv.gz")):
                name = f.name.removesuffix(".csv.gz").lower()
                tables[name] = f
        return tables

    def find_note_tables(self) -> dict[str, Path]:
        """Discover MIMIC-IV-Note CSV.gz tables.

        Returns a dict mapping table name (e.g. "discharge", "radiology")
        to file path. Returns empty dict if note_path is None or doesn't exist.
        """
        if self.note_path is None or not self.note_path.exists():
            return {}
        tables: dict[str, Path] = {}
        for f in sorted(self.note_path.glob("*.csv.gz")):
            name = f.name.removesuffix(".csv.gz").lower()
            tables[name] = f
        return tables


# Default paths; override with MIMIC_III_PATH / MIMIC_IV_PATH environment variables
_MIMIC3_DEFAULT = Path.home() / "projects/mimic-iii/physionet.org/files/mimiciii/1.4"
_MIMIC4_DEFAULT = Path.home() / "projects/mimic-iv/physionet.org/files/mimiciv/3.1"
_MIMIC4_NOTE_DEFAULT = (
    Path.home() / "projects/mimic-iv-note/physionet.org/files/mimic-iv-note/2.2/note"
)

DATASETS: dict[str, DatasetConfig] = {
    "mimic-iii": DatasetConfig(
        name="MIMIC-III v1.4",
        base_path=Path(os.environ.get("MIMIC_III_PATH", str(_MIMIC3_DEFAULT))),
        uppercase_filenames=True,
    ),
    "mimic-iv": DatasetConfig(
        name="MIMIC-IV v3.1",
        base_path=Path(os.environ.get("MIMIC_IV_PATH", str(_MIMIC4_DEFAULT))),
        subdirs=("hosp", "icu"),
        note_path=Path(os.environ.get("MIMIC_IV_NOTE_PATH", str(_MIMIC4_NOTE_DEFAULT))),
    ),
}

# Tables too large to count by default in row count operations
LARGE_TABLES = frozenset(
    {
        "chartevents",
        "labevents",
        "inputevents",
        "inputevents_cv",
        "inputevents_mv",
        "noteevents",
        "discharge",
        "radiology",
    }
)
