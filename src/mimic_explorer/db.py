"""DuckDB connection and query helpers for reading MIMIC CSV.gz files."""

from pathlib import Path

import duckdb


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
) -> "duckdb.DuckDBPyRelation":
    """Return a sample of rows from a CSV.gz file as a DuckDB relation."""
    return conn.execute(f"SELECT * FROM {table_ref(file_path)} LIMIT {limit}")
