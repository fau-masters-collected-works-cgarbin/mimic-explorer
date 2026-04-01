"""Database Schema: how MIMIC tables connect and what they contain."""

from pathlib import Path

import pandas as pd
import streamlit as st

from mimic_explorer.config import DATASETS, LARGE_TABLES
from mimic_explorer.db import column_info, get_connection, row_count

st.title("Database Schema")

dataset = DATASETS[st.session_state["dataset_key"]]
st.caption(f"Showing: {dataset.name}")
tables = dataset.find_tables()
is_mimic3 = dataset.uppercase_filenames
ICU_KEY = dataset.col("icu_key")


# -- Scan schema --


@st.cache_data(show_spinner="Scanning schema...")
def scan_schema(dataset_name: str, tables_map: dict[str, str]):
    """For each table, detect join keys and read column details."""
    conn = get_connection()
    result = {}
    for table_name, file_path in sorted(tables_map.items()):
        cols = column_info(conn, Path(file_path))
        col_names_lower = {c["name"].lower() for c in cols}
        result[table_name] = {
            "subject_id": "subject_id" in col_names_lower,
            "hadm_id": "hadm_id" in col_names_lower,
            "icu_key": ICU_KEY.lower() in col_names_lower,
            "columns": cols,
        }
    return result


schema = scan_schema(dataset.name, {k: str(v) for k, v in tables.items()})


@st.cache_data(show_spinner="Counting rows...")
def get_row_count(
    dataset_name: str, table_name: str, file_path_str: str, *, skip_large: bool = True
) -> int | None:
    """Cached row count. Returns None if skipped."""
    if skip_large and table_name in LARGE_TABLES:
        return None
    conn = get_connection()
    return row_count(conn, Path(file_path_str))


# -- Group tables by connectivity level --
# Tables are classified by their highest join key. This mirrors the three-level
# hierarchy (patient -> admission -> ICU stay) that structures all of MIMIC.
# Tables without any join key are dictionary/lookup tables.

CORE_TABLES = {"patients", "admissions", "icustays"}

icu_level = []
admission_level = []
patient_only = []
no_keys = []

for table_name, keys in sorted(schema.items()):
    if table_name in CORE_TABLES:
        continue
    if keys["icu_key"]:
        icu_level.append(table_name)
    elif keys["hadm_id"]:
        admission_level.append(table_name)
    elif keys["subject_id"]:
        patient_only.append(table_name)
    else:
        no_keys.append(table_name)


# -- How tables connect --

st.subheader("How tables connect")

st.markdown(f"""
{dataset.name} is organized around a three-level hierarchy. Every table connects to at least one of
these identifiers, and understanding this hierarchy is the key to joining tables correctly.

- **`subject_id`** identifies a unique patient. Every clinical table has this.
- **`hadm_id`** identifies a single hospital admission. One patient can have multiple admissions.
- **`{ICU_KEY}`** identifies a single ICU stay. One admission can involve multiple ICU stays
  (e.g., a patient transferred out of the ICU and later readmitted).
""")

admission_label = "\\n".join(admission_level)
icu_label = "\\n".join(icu_level)
patient_label = "\\n".join(patient_only)
dict_label = "\\n".join(no_keys)

# Build a Graphviz DOT diagram showing the join hierarchy. Core tables are
# colored by level (blue=patient, green=admission, orange=ICU). Clinical
# tables hang off their highest join level with dashed edges. Dictionary
# tables connect to their target clinical tables with dotted edges.
dot = f"""
digraph MIMIC {{
    rankdir=LR;
    node [shape=box, style=filled, fillcolor="#f0f2f6", fontname="Helvetica"];
    edge [fontname="Helvetica", fontsize=10];

    patients [label="patients\\n(one row per patient)", fillcolor="#d4e6f1"];
    admissions [label="admissions\\n(one row per admission)", fillcolor="#d5f5e3"];
    icustays [label="icustays\\n(one row per ICU stay)", fillcolor="#fdebd0"];

    patients -> admissions [label="subject_id\\n(1 to many)"];
    admissions -> icustays [label="hadm_id\\n(1 to many)"];

    // Clinical tables that hang off each level
    node [shape=note, fillcolor="#fafafa", fontsize=10];

    admission_tables [label="{admission_label}"];
    icu_tables [label="{icu_label}"];

    admissions -> admission_tables [style=dashed, label="hadm_id"];
    icustays -> icu_tables [style=dashed, label="{ICU_KEY}"];
"""

if patient_only:
    dot += f"""
    patient_tables [label="{patient_label}"];
    patients -> patient_tables [style=dashed, label="subject_id"];
"""

# Dictionary/lookup table relationships: map each dictionary table to the
# clinical table group it describes and the join key used. These differ
# between versions (e.g., MIMIC-III uses d_cpt/caregivers, MIMIC-IV uses
# d_hcpcs/caregiver) and have different key column names.
DICT_LINKS_MIMIC3 = {
    "d_icd_diagnoses": [("admission_tables", "ICD9_CODE")],
    "d_icd_procedures": [("admission_tables", "ICD9_CODE")],
    "d_labitems": [("admission_tables", "ITEMID")],
    "d_items": [("icu_tables", "ITEMID")],
    "d_cpt": [("admission_tables", "CPT_CD")],
    "caregivers": [("icu_tables", "CGID")],
}
DICT_LINKS_MIMIC4 = {
    "d_icd_diagnoses": [("admission_tables", "icd_code")],
    "d_icd_procedures": [("admission_tables", "icd_code")],
    "d_labitems": [("admission_tables", "itemid")],
    "d_items": [("icu_tables", "itemid")],
    "d_hcpcs": [("admission_tables", "hcpcs_cd")],
    "caregiver": [("icu_tables", "caregiver_id")],
}
dict_links = DICT_LINKS_MIMIC3 if is_mimic3 else DICT_LINKS_MIMIC4

for tbl in no_keys:
    safe_id = tbl.replace("-", "_")
    dot += f'    {safe_id} [label="{tbl}", shape=note, fillcolor="#fafafa", fontsize=10];\n'
    if tbl in dict_links:
        for target, key in dict_links[tbl]:
            dot += f'    {safe_id} -> {target} [style=dotted, label="{key}", fontsize=9];\n'

dot += "}"
st.graphviz_chart(dot)


# -- Tables by connectivity level --

st.subheader("Tables by connectivity level")

include_large = st.checkbox(
    "Include row counts for large tables (CHARTEVENTS, LABEVENTS, etc.). Slow on first run.",
    value=False,
)


def render_table_group(title, description, table_names):
    """Render a connectivity group with expanders for each table."""
    if not table_names:
        return
    st.markdown(f"**{title}**: {description}")
    for name in table_names:
        info = schema[name]
        cols = info["columns"]
        with st.expander(f"{name} ({len(cols)} columns)"):
            # Join keys
            present_keys = []
            if info["subject_id"]:
                present_keys.append("subject_id")
            if info["hadm_id"]:
                present_keys.append("hadm_id")
            if info["icu_key"]:
                present_keys.append(ICU_KEY)
            if present_keys:
                st.markdown("Join keys: " + ", ".join(f"`{k}`" for k in present_keys))

            # Row count
            if name in LARGE_TABLES and not include_large:
                st.caption("Large table, row count skipped")
            else:
                count = get_row_count(
                    dataset.name, name, str(tables[name]), skip_large=not include_large
                )
                if count is not None:
                    st.metric("Rows", f"{count:,}")
                else:
                    st.caption("Large table, row count skipped")

            # Column details
            st.dataframe(pd.DataFrame(cols), hide_index=True)


core_tables = [t for t in sorted(CORE_TABLES) if t in schema]
render_table_group(
    "Core tables",
    "the three tables that define the join hierarchy",
    core_tables,
)
render_table_group(
    f"ICU-level tables (have `{ICU_KEY}`)",
    "one row per ICU event or measurement",
    icu_level,
)
render_table_group(
    "Admission-level tables (have `hadm_id`)",
    "one row per event within an admission",
    admission_level,
)
render_table_group(
    "Patient-level tables (have `subject_id` only)",
    "one row per patient or per patient event",
    patient_only,
)
render_table_group(
    "Lookup/dictionary tables (no join keys)",
    "reference data like ICD code descriptions",
    no_keys,
)


# -- Common join patterns --

st.subheader("Common join patterns")

st.markdown(f"""
**Get patient demographics for an ICU stay:**
```sql
SELECT p.*, i.*
FROM icustays i
JOIN patients p ON i.subject_id = p.subject_id
```

**Get diagnoses for an admission:**
```sql
SELECT a.*, d.*
FROM admissions a
JOIN diagnoses_icd d ON a.hadm_id = d.hadm_id
```

**Get chart events for a specific ICU stay:**
```sql
SELECT c.*
FROM chartevents c
WHERE c.{ICU_KEY} = <some_stay_id>
```

These patterns compose: you can chain joins across all three levels to connect any tables that
share a key. The grouping above tells you which key to use.
""")
