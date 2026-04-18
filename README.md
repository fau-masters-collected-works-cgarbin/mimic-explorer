# MIMIC Explorer

Explore [MIMIC-III](https://physionet.org/content/mimiciii/) and [MIMIC-IV](https://physionet.org/content/mimiciv/) clinical datasets interactively. Reads CSV.gz files directly with DuckDB. No ETL, no database setup.

## Getting started

You need local copies of the MIMIC CSV.gz files (downloaded from PhysioNet after [credentialing](https://mimic.mit.edu/docs/gettingstarted/)).

Install dependencies and run:

```bash
uv sync --all-groups
uv run streamlit run app.py
```

By default the app looks for datasets at:

- MIMIC-III: `~/projects/mimic-iii/physionet.org/files/mimiciii/1.4`
- MIMIC-IV: `~/projects/mimic-iv/physionet.org/files/mimiciv/3.1`
- MIMIC-IV-Note: `~/projects/mimic-iv-note/physionet.org/files/mimic-iv-note/2.2/note`

All datasets are optional.

MIMIC-IV-Note is a separate PhysioNet module containing clinical notes for MIMIC-IV (discharge summaries and radiology reports). Download it from [PhysioNet](https://physionet.org/content/mimic-iv-note/) after credentialing. The Clinical Timeline page uses this module for notes when working with MIMIC-IV.

To use different paths, set environment variables before launching:

```bash
# All optional, set only the ones you need
export MIMIC_III_PATH=/your/path/to/mimiciii/1.4
export MIMIC_IV_PATH=/your/path/to/mimiciv/3.1
export MIMIC_IV_NOTE_PATH=/your/path/to/mimic-iv-note/2.2/note
uv run streamlit run app.py
```

Switch between MIMIC-III and MIMIC-IV at any time using the dataset selector in the sidebar.

## What each page does

If you're new to MIMIC, work through the pages in order.

**Dataset at a Glance** gives you the scale of the dataset: how many patients, how many hospital admissions, how many ICU stays, mortality rate, and median length of stay. Each number includes a plain-language explanation of what it means clinically.

**Database Schema** shows how tables relate to each other through the `subject_id` / `hadm_id` / `icustay_id` (MIMIC-III) or `stay_id` (MIMIC-IV) join key hierarchy. Tables are grouped by connectivity level, each expandable to show column details. Includes an interactive diagram and ready-to-use join patterns.

**Clinical Insights** profiles the patient population: demographics, top diagnoses, procedures, lab tests, and length-of-stay distributions. Useful for understanding the dataset before designing cohort filters.

**Clinical Timeline** shows what happened during a single hospital stay and when. Clinical notes, abnormal labs, unit transfers, and medication changes are plotted on one timeline. You can pick a random admission or enter a specific one. Uses NOTEEVENTS for MIMIC-III and the separate MIMIC-IV-Note module for MIMIC-IV; structured events (labs, transfers, medications) are available for both versions.

**Community References** collects links to external MIMIC resources: official documentation, tutorials, derived clinical concepts, and BigQuery access.

<details>
<summary>How this relates to existing MIMIC resources</summary>

The MIMIC ecosystem already has good resources, but they serve different purposes.

**Official documentation** at [mimic.mit.edu](https://mimic.mit.edu/docs/) provides thorough column-level descriptions for each table. It's the authoritative reference, but it's organized as individual pages per table with no cross-table navigation, no visual schema map, and no dataset-level summary statistics.

**mimic-code** ([github.com/MIT-LCP/mimic-code](https://github.com/MIT-LCP/mimic-code)) is the official community repository with PostgreSQL/BigQuery build scripts, derived concept SQL, and tutorial notebooks. It's aimed at researchers who already have a working mental model of the data and need to compute specific clinical concepts.

**BigQuery on GCP** lets credentialed researchers query MIMIC-IV directly in the browser, but requires GCP access and has no schema diagrams or dataset-level statistics.

**Tutorials** exist (Alistair Johnson's [data tutorial](https://alistairewj.github.io/talk/2020-mimic-iv-data-tutorial/) and [analysis tutorial](https://alistairewj.github.io/talk/2020-mimic-iv-analysis-tutorial/), a [Colab notebook](https://colab.research.google.com/drive/1REu-ofzNzqsTT1cxLHIegPB0nGmwKaM0), and [workshop materials](https://github.com/MIT-LCP/mimic-workshop)) but they're scattered and assume some familiarity with the dataset structure.

**SchemaSpy** ([lcp.mit.edu/mimic-schema-spy](https://lcp.mit.edu/mimic-schema-spy/)) is the closest thing to an interactive schema explorer. Generated from a PostgreSQL load of MIMIC-III, it provides clickable table views, foreign key diagrams, column-level metadata, and relationship navigation. It's thorough for schema structure, but covers MIMIC-III only (generated in 2017), requires a Postgres load to regenerate, shows metadata without actual data browsing, and doesn't provide dataset-level clinical context. A [GitHub issue](https://github.com/MIT-LCP/mimic-code/issues/183) also collected community-contributed ER diagrams, and the MIMIC-IV [Scientific Data paper](https://www.nature.com/articles/s41597-022-01899-x) includes schema figures.

**What this tool adds**: dataset-level statistics with clinical context, interactive exploration of CSV.gz files with no database setup, and support for both MIMIC-III and MIMIC-IV. SchemaSpy's FK diagrams are more detailed for schema relationships specifically.

</details>

## AI Disclosure

I used a coding agent (Claude Code with Opus) in this work. I reviewed its output and am responsible for the result.
