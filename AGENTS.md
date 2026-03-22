# Agent Guidelines

## Project overview

Streamlit database explorer for MIMIC-III and MIMIC-IV clinical datasets. Uses DuckDB to query CSV.gz files directly (no ETL, no database). The goal is to understand the data before building experiments.

## Architecture

- `app.py` -- Streamlit entry point, dataset selector sidebar, page navigation. UI only.
- `src/mimic_explorer/config.py` -- Dataset path configuration and table discovery. No UI imports.
- `src/mimic_explorer/db.py` -- DuckDB connection and query helpers for reading MIMIC CSV.gz files. No UI imports.
- `src/mimic_explorer/stats.py` -- Pre-compute and cache all static dataset statistics to disk. Used by Dataset at a Glance and Clinical Insights pages.
- `src/mimic_explorer/timeline_queries.py` -- Data-fetching queries for the Clinical Timeline page. No UI imports.
- `pages/dataset_at_a_glance.py` -- Key dataset metrics and contextual explanations. UI only, reads from cached stats.
- `pages/database_schema.py` -- Join key hierarchy, table details, join patterns. UI only.
- `pages/clinical_insights.py` -- Demographics, distributions, table coverage, data quality. UI only, reads from cached stats.
- `pages/note_timeline.py` -- Clinical timeline: notes alongside labs, transfers, medications across hospital stays. UI only.
- `pages/community_references.py` -- Links to external MIMIC resources. Static content.

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

## Data protection

MIMIC is a restricted-access dataset. Treat all patient data as sensitive, even though it is de-identified.

- Never commit MIMIC data files (CSV, CSV.gz, Parquet) to the repository. Source data lives outside the repo.
- Never write patient-level data or query results to files inside the repo.
- `.mimic_explorer_cache/` stores derived statistics on disk. It is gitignored and must stay that way.
- Any new on-disk cache or output path must be added to `.gitignore` before the commit that introduces it.
- Test fixtures must use synthetic data only (see `tests/conftest.py`). Never copy real MIMIC rows into tests.

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

Run tests after every change to `config.py`, `db.py`, or `stats.py`.

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

- Python 3.12+ features are fine.
- Type hints on function signatures in logic modules (`config.py`, `db.py`).
- Annotations optional in Streamlit pages and `app.py`.
- S608 (SQL injection) suppressed for `table_ref()` interpolation -- these SQL fragments are built from local file paths discovered by `config.py`, not from user input.
- Use DuckDB parameterized queries (`$1`, `$2`, ...) for any value that originates from user input (e.g., HADM_ID from a text input, note ID from a selectbox). Table references from `table_ref()` and `note_union_ref()` cannot be parameterized and are interpolated directly.
- Page ordering is controlled via `st.navigation()` in `app.py`, not filename prefixes. Pages must not call `st.set_page_config()`.

## Testing philosophy

- Test `config.py`, `db.py`, and `stats.py` with synthetic CSV.gz fixtures (see `tests/conftest.py`).
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
