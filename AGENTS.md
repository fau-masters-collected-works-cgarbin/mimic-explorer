# Agent Guidelines

## Project overview

Streamlit database explorer for MIMIC-III and MIMIC-IV clinical datasets. Uses DuckDB to query CSV.gz files directly (no ETL, no database). Phase 0a of the dissertation execution plan: understand the data before building experiments.

## Architecture

- `app.py` -- Streamlit entry point, dataset selector sidebar. UI only.
- `src/mimic_explorer/config.py` -- Dataset path configuration, table discovery. No UI imports.
- `src/mimic_explorer/db.py` -- DuckDB connection, `table_ref()` resolver, query helpers. No UI imports.
- `pages/1_schema_overview.py` -- Table list with row counts and column info. UI only, uses db and config.
- `pages/2_table_browser.py` -- Sample rows, column stats, filter/sort. UI only, uses db and config.

## Setup

```bash
uv sync --all-groups
prek install  # or: pre-commit install
```

## Running the app

```bash
uv run streamlit run app.py
```

## Running tests

```bash
uv run pytest tests/ -v
```

Run tests after every change to `config.py` or `db.py`.

## Linting and formatting

```bash
uv run ruff check .
uv run ruff format .
```

Pre-commit hooks run ruff automatically on commit.

## Code style

- Python 3.11+ features are fine.
- Type hints on function signatures in logic modules (`config.py`, `db.py`).
- Annotations optional in Streamlit pages and `app.py`.
- S608 (SQL injection) suppressed for DuckDB file reads -- all SQL is built from local file paths, not user input.
- N999 suppressed for pages -- Streamlit requires numeric prefixes for page ordering.

## Testing philosophy

- Test `config.py` and `db.py` with synthetic CSV.gz fixtures (see `tests/conftest.py`).
- Don't test Streamlit pages -- business logic lives in the logic modules.
- Mock nothing for now -- DuckDB reads temp files directly in tests.

## Key design decisions

- DuckDB reads CSV.gz directly via `read_csv_auto()`. No ETL step.
- `table_ref(path)` returns a SQL fragment: `read_csv_auto('/path/to/file.csv.gz')`.
- Large tables (CHARTEVENTS, LABEVENTS) are skipped by default in row counts.
- MIMIC-III uses flat directory with UPPERCASE filenames; MIMIC-IV uses hosp/icu subdirs with lowercase.
