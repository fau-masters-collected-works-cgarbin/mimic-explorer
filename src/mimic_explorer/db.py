"""DuckDB connection and query helpers for reading MIMIC CSV.gz files."""

from __future__ import annotations

from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a DuckDB in-memory connection."""
    return duckdb.connect()


def table_ref(file_path: Path) -> str:
    """Return a DuckDB read_csv_auto expression for a CSV.gz file.

    Usage in SQL: f"SELECT * FROM {table_ref(path)} LIMIT 10"
    """
    return f"read_csv_auto('{file_path}')"


def row_count(conn: duckdb.DuckDBPyConnection, file_path: Path) -> int:
    """Count rows in a CSV.gz file."""
    result = conn.execute(f"SELECT count(*) FROM {table_ref(file_path)}").fetchone()
    return result[0] if result else 0


def column_info(conn: duckdb.DuckDBPyConnection, file_path: Path) -> list[dict[str, str]]:
    """Get column names and inferred types for a CSV.gz file.

    Uses LIMIT 0 query and reads column metadata from cursor description,
    since DESCRIBE doesn't work directly with read_csv_auto().
    """
    cursor = conn.execute(f"SELECT * FROM {table_ref(file_path)} LIMIT 0")
    return [{"name": col[0], "type": str(col[1])} for col in cursor.description]


def sample_rows(
    conn: duckdb.DuckDBPyConnection,
    file_path: Path,
    limit: int = 100,
) -> pd.DataFrame:
    """Return a sample of rows from a CSV.gz file as a DataFrame."""
    return conn.execute(f"SELECT * FROM {table_ref(file_path)} LIMIT {limit}").fetchdf()


def resolve_refs(tables: dict[str, Path], names: list[str]) -> dict[str, str | None]:
    """Resolve table names to DuckDB read_csv_auto expressions.

    Returns a dict mapping each requested name to its SQL reference,
    or None if the table is not present in the dataset.
    """
    return {name: table_ref(tables[name]) if name in tables else None for name in names}


# Only the main note tables, not the *_detail variants (different schema)
_NOTE_TABLE_LABELS: dict[str, str] = {
    "discharge": "Discharge summary",
    "radiology": "Radiology",
}


def note_union_ref(note_tables: dict[str, Path]) -> str | None:
    """Build a UNION ALL SQL fragment for MIMIC-IV-Note tables.

    Each table gets a synthetic ``category`` column with a human-readable label.
    Returns a parenthesised subquery aliased as ``noteevents``, or ``None``
    if *note_tables* is empty.
    """
    if not note_tables:
        return None
    selects = []
    for name, path in note_tables.items():
        if name not in _NOTE_TABLE_LABELS:
            continue
        label = _NOTE_TABLE_LABELS[name]
        selects.append(
            f"SELECT note_id, subject_id, hadm_id, note_type, note_seq, "
            f"charttime, storetime, text, '{label}' AS category "
            f"FROM {table_ref(path)}"
        )
    if not selects:
        return None
    union = " UNION ALL ".join(selects)
    return f"({union}) AS noteevents"


def scalar_query(conn: duckdb.DuckDBPyConnection, sql: str) -> object:
    """Run a SQL query and return the single scalar result.

    The SQL should reference tables via table_ref(), e.g.:
        scalar_query(conn, f"SELECT count(*) FROM {table_ref(path)}")
    """
    result = conn.execute(sql).fetchone()
    return result[0] if result else None
