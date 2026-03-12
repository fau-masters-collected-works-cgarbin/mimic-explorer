# MIMIC Explorer

Interactive Streamlit app for exploring MIMIC-III and MIMIC-IV clinical datasets. Reads CSV.gz files directly with DuckDB -- no ETL, no database setup.

Built as Phase 0a of a dissertation project: understand the data before building experiments.

## What it does

- **Dataset at a Glance**: Key numbers (patient count, admissions, ICU stays, mortality rate, median length of stay) with plain-language explanations of what they mean clinically.
- **Table Relationships**: Visual diagram of the `subject_id` / `hadm_id` / `icustay_id` join key hierarchy, a matrix showing which keys each table contains, and ready-to-use join patterns.
- **Schema Overview**: Every table with row counts, column counts, and column types.
- **Table Browser**: Browse rows with filtering, sorting, and column-level statistics.

## How this relates to existing MIMIC resources

The MIMIC ecosystem already has good resources, but they serve different purposes.

**Official documentation** at [mimic.mit.edu](https://mimic.mit.edu/docs/iv/) provides thorough column-level descriptions for each table. It's the authoritative reference, but it's organized as individual pages per table with no cross-table navigation, no visual schema map, and no dataset-level summary statistics. You learn what a column means, but not how the dataset fits together.

**mimic-code** ([github.com/MIT-LCP/mimic-code](https://github.com/MIT-LCP/mimic-code)) is the official community repository with PostgreSQL/BigQuery build scripts, derived concept SQL, and tutorial notebooks. It's aimed at researchers who already have a working mental model of the data and need to compute specific clinical concepts.

**BigQuery on GCP** lets credentialed researchers query MIMIC-IV directly in the browser. It functions as a de facto data browser, but requires GCP access and doesn't provide orientation or relationship context.

**Tutorials** exist (Alistair Johnson's [data tutorial](https://alistairewj.github.io/talk/2020-mimic-iv-data-tutorial/) and [analysis tutorial](https://alistairewj.github.io/talk/2020-mimic-iv-analysis-tutorial/), a [Colab notebook](https://colab.research.google.com/drive/1REu-ofzNzqsTT1cxLHIegPB0nGmwKaM0), and [workshop materials](https://github.com/MIT-LCP/mimic-workshop)) but they're scattered and assume some familiarity with the dataset structure.

**SchemaSpy** ([lcp.mit.edu/mimic-schema-spy](https://lcp.mit.edu/mimic-schema-spy/)) is the closest thing to an interactive schema explorer. Generated from a PostgreSQL load of MIMIC-III, it provides clickable table views, foreign key diagrams, column-level metadata, and relationship navigation. It's thorough for schema structure, but covers MIMIC-III only (generated in 2017), requires a Postgres load to regenerate, shows metadata without actual data browsing, and doesn't provide dataset-level clinical context. A [GitHub issue](https://github.com/MIT-LCP/mimic-code/issues/183) also collected community-contributed ER diagrams, and the MIMIC-IV [Scientific Data paper](https://www.nature.com/articles/s41597-022-01899-x) includes schema figures.

**What this tool adds**: dataset-level orientation (key statistics with clinical context), live data browsing against CSV.gz files with no database setup, and support for both MIMIC-III and MIMIC-IV. It's the "guided tour" layer that sits between the official docs (reference) and mimic-code (analysis). For schema relationships specifically, SchemaSpy's FK diagrams are more detailed than what we show -- our join key matrix is a simpler view focused on the three core identifiers that matter most for getting started.

## Setup

```bash
uv sync --all-groups
pre-commit install
```

## Running

```bash
uv run streamlit run app.py
```

Update dataset paths in `src/mimic_explorer/config.py` to point to your local MIMIC CSV.gz files.
