"""Dataset path configuration for MIMIC-III and MIMIC-IV."""

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


# Default dataset configurations -- adjust paths to match your local setup
DATASETS: dict[str, DatasetConfig] = {
    "mimic-iii": DatasetConfig(
        name="MIMIC-III v1.4",
        base_path=Path.home() / "projects/mimic-iii/physionet.org/files/mimiciii/1.4",
        uppercase_filenames=True,
    ),
    "mimic-iv": DatasetConfig(
        name="MIMIC-IV v3.1",
        base_path=Path.home() / "projects/mimic-iv/physionet.org/files/mimiciv/3.1",
        subdirs=("hosp", "icu"),
    ),
}

# Tables that are very large and slow to count -- skip by default in row count operations
LARGE_TABLES = frozenset({"chartevents", "labevents", "inputevents_cv", "inputevents_mv"})
