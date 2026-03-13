"""Dataset path configuration for MIMIC-III and MIMIC-IV."""

import os
from dataclasses import dataclass
from pathlib import Path


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
                        # .stem strips .gz, need to strip .csv too
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

# Tables that are very large and slow to count -- skip by default in row count operations
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
