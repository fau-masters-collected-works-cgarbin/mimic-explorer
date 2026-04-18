"""DuckDB connection and query helpers for reading MIMIC CSV.gz files."""

from __future__ import annotations

from typing import TYPE_CHECKING

import duckdb

if TYPE_CHECKING:
    from pathlib import Path

    from mimic_explorer.config import DatasetConfig


def get_connection() -> duckdb.DuckDBPyConnection:
    """Return a fresh DuckDB in-memory connection.

    Each call creates a new connection. This is intentional: DuckDB connections
    are not thread-safe, so callers in threaded contexts (e.g. timeline_queries)
    need their own connection. The overhead is negligible since there is no
    persistent database to open.
    """
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

    Uses a LIMIT 0 query and reads column metadata from the cursor description.
    DuckDB's DESCRIBE statement doesn't work with read_csv_auto() expressions,
    so we use this workaround instead.
    """
    cursor = conn.execute(f"SELECT * FROM {table_ref(file_path)} LIMIT 0")
    return [{"name": col[0], "type": str(col[1])} for col in cursor.description]


def resolve_refs(tables: dict[str, Path], names: list[str]) -> dict[str, str | None]:
    """Resolve table names to DuckDB read_csv_auto expressions.

    Returns a dict mapping each requested name to its SQL reference,
    or None if the table is not present in the dataset.
    """
    return {name: table_ref(tables[name]) if name in tables else None for name in names}


# Only the main note tables. The *_detail variants (discharge_detail, etc.)
# have a different schema (field_name/field_value columns) and can't be
# UNIONed with the main tables.
_NOTE_TABLE_LABELS: dict[str, str] = {
    "discharge": "Discharge summary",
    "radiology": "Radiology",
}


def note_union_ref(note_tables: dict[str, Path]) -> str | None:
    """Build a UNION ALL SQL fragment for MIMIC-IV-Note tables.

    MIMIC-IV-Note splits notes into separate tables (discharge, radiology) instead
    of the single NOTEEVENTS table in MIMIC-III. This function UNIONs them back
    together with a synthetic ``category`` column so downstream code can treat
    both versions uniformly. Returns a parenthesised subquery aliased as
    ``noteevents``, or ``None`` if *note_tables* is empty.
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


def resolve_note_ref(cfg: DatasetConfig) -> str | None:
    """Return a SQL reference for the unified notes view, or None if unavailable.

    MIMIC-III stores notes in a single NOTEEVENTS table inside the main dataset.
    MIMIC-IV moved notes to the separate MIMIC-IV-Note module, split across
    discharge and radiology tables, which this function UNIONs back together so
    callers can treat both versions uniformly.
    """
    if cfg.uppercase_filenames:
        path = cfg.find_tables().get("noteevents")
        return table_ref(path) if path else None
    note_tables = cfg.find_note_tables()
    return note_union_ref(note_tables) if note_tables else None


def scalar_query(conn: duckdb.DuckDBPyConnection, sql: str) -> object:
    """Run a SQL query and return the single scalar result.

    The SQL should reference tables via table_ref(), e.g.:
        scalar_query(conn, f"SELECT count(*) FROM {table_ref(path)}")
    """
    result = conn.execute(sql).fetchone()
    return result[0] if result else None
