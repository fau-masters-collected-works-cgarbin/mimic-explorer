# Agent Guidelines

## Project overview

Streamlit database explorer for MIMIC-III and MIMIC-IV clinical datasets. Uses DuckDB to query CSV.gz files directly (no ETL, no database). Phase 0a of the dissertation execution plan: understand the data before building experiments.

## Architecture

- `app.py` -- Streamlit entry point, dataset selector sidebar, `st.navigation()` page routing. UI only.
- `src/mimic_explorer/config.py` -- Dataset path configuration, table discovery, `LARGE_TABLES` set. No UI imports.
- `src/mimic_explorer/db.py` -- DuckDB connection, `table_ref()` resolver, `note_union_ref()` for MIMIC-IV-Note UNION queries, query helpers (`scalar_query`, `resolve_refs`, `column_info`, `row_count`, `sample_rows`). No UI imports.
- `pages/dataset_at_a_glance.py` -- Key dataset metrics and contextual explanations for newcomers. UI only, uses db and config.
- `pages/database_schema.py` -- Join key hierarchy, tables grouped by connectivity with column details in expanders, join patterns. UI only, uses db and config.
- `pages/clinical_insights.py` -- Distributions: top diagnoses/procedures/labs, demographics, LOS. UI only, uses db.
- `pages/note_timeline.py` -- Clinical timeline across hospital stays. Shows notes alongside structured clinical events (abnormal labs, unit transfers, medication starts/stops) on a unified timeline. Also includes note category overview, temporal density, note-to-note intervals, note text viewer. UI only, uses db and config. MIMIC-III uses NOTEEVENTS + LABEVENTS/TRANSFERS/PRESCRIPTIONS; MIMIC-IV uses MIMIC-IV-Note module + hosp tables (labevents/transfers/prescriptions).
- `pages/community_references.py` -- Links to external MIMIC resources. Static content, no data queries.

## MIMIC schema reference

**Read [`docs/mimic_schema_reference.md`](docs/mimic_schema_reference.md) before writing any version-aware SQL.** It has verified column names, version differences, and join patterns for both MIMIC-III and MIMIC-IV. Do not derive schema at runtime (e.g., querying column names to decide which columns exist) when the information is already in the reference. The reference is the source of truth for column names, table layouts, and version-specific differences.

## Git workflow

- Work in worktrees (`isolation: "worktree"`), not the main working directory.
- Always rebase, never merge. Keep history linear.
- Push directly to `main` when done -- no PRs for single-author work.
- Before pushing, sync and push in one sequence from the worktree. Resolve any conflicts, then run lint and tests before pushing:
  ```bash
  git fetch origin && git rebase origin/main && git push origin HEAD:main
  ```
- After pushing, update the local main branch from the main working directory:
  ```bash
  git fetch origin && git rebase origin/main
  ```
- Sync with main before starting significant new work in a long-running worktree, to avoid large conflict sets at merge time.

## Setup

```bash
uv sync --all-groups
pre-commit install
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

Schema validation tests (require local MIMIC data, excluded from default runs):

```bash
uv run pytest tests/test_schema_reference.py -m schema -v
```

## Linting and formatting

```bash
uv run ruff check .
uv run ruff format .
```

Pre-commit hooks run automatically on commit: ruff (lint + format), trailing-whitespace, end-of-file-fixer, check-yaml, check-merge-conflict.

## Code style

- Python 3.11+ features are fine.
- Type hints on function signatures in logic modules (`config.py`, `db.py`).
- Annotations optional in Streamlit pages and `app.py`.
- S608 (SQL injection) suppressed for `table_ref()` interpolation -- these SQL fragments are built from local file paths discovered by `config.py`, not from user input.
- Use DuckDB parameterized queries (`$1`, `$2`, ...) for any value that originates from user input (e.g., HADM_ID from a text input, note ID from a selectbox). Table references from `table_ref()` and `note_union_ref()` cannot be parameterized and are interpolated directly.
- Page ordering is controlled via `st.navigation()` in `app.py`, not filename prefixes. Pages must not call `st.set_page_config()`.

## Testing philosophy

- Test `config.py` and `db.py` with synthetic CSV.gz fixtures (see `tests/conftest.py`).
- Don't test Streamlit pages -- business logic lives in the logic modules. If page-level logic grows complex enough to warrant tests, extract it into `db.py` or `config.py` first.
- Mock nothing for now -- DuckDB reads temp files directly in tests.

## Key design decisions

- DuckDB reads CSV.gz directly via `read_csv_auto()`. No ETL step.
- `table_ref(path)` returns a SQL fragment: `read_csv_auto('/path/to/file.csv.gz')`.
- Tables listed in `LARGE_TABLES` (in `config.py`) are skipped by default in row count operations.
- MIMIC-III uses flat directory with UPPERCASE filenames; MIMIC-IV uses hosp/icu subdirs with lowercase.

## Streamlit caching

- `st.cache_data` parameters prefixed with `_` are excluded from the cache key.
- Always include the dataset name as a non-prefixed parameter so the cache invalidates when the user switches datasets.
- ARG001 is suppressed for pages because cache-key-only parameters are intentional.
- `st.cache_data` cannot hash `Path` objects. Convert to `str` before passing as cache key parameters.
- Use `width="stretch"` instead of `use_container_width=True` for `st.plotly_chart` and `st.dataframe`.
