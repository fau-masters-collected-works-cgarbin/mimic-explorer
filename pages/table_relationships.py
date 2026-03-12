"""Table Relationships -- how MIMIC tables connect through join keys."""

import streamlit as st

from mimic_explorer.config import DatasetConfig
from mimic_explorer.db import column_info, get_connection

st.title("Table Relationships")

if "dataset" not in st.session_state:
    st.warning("Select a dataset from the main page first.")
    st.stop()

dataset: DatasetConfig = st.session_state["dataset"]
st.caption(f"Showing: {dataset.name}")
tables = dataset.find_tables()
is_mimic3 = dataset.uppercase_filenames

# The three join keys that define MIMIC's structure
JOIN_KEYS = {"subject_id", "hadm_id", "icustay_id" if is_mimic3 else "stay_id"}
ICU_KEY = "icustay_id" if is_mimic3 else "stay_id"


# -- Scan all tables for join keys --


@st.cache_data(show_spinner="Scanning table columns...")
def scan_join_keys(dataset_name: str, tables_map: dict[str, str]):
    """For each table, detect which join keys are present."""
    conn = get_connection()
    result = {}
    for table_name, file_path in sorted(tables_map.items()):
        cols = column_info(conn, file_path)
        col_names_lower = {c["name"].lower() for c in cols}
        result[table_name] = {
            "subject_id": "subject_id" in col_names_lower,
            "hadm_id": "hadm_id" in col_names_lower,
            "icu_key": ICU_KEY.lower() in col_names_lower,
            "all_columns": [c["name"] for c in cols],
        }
    return result


table_keys = scan_join_keys(dataset.name, {k: str(v) for k, v in tables.items()})

# -- Relationship diagram --

st.subheader("How tables connect")

st.markdown(f"""
{dataset.name} is organized around a three-level hierarchy. Every table connects to at least one of
these identifiers, and understanding this hierarchy is the key to joining tables correctly.

- **`subject_id`** identifies a unique patient. Every clinical table has this.
- **`hadm_id`** identifies a single hospital admission. One patient can have multiple admissions.
- **`{ICU_KEY}`** identifies a single ICU stay. One admission can involve multiple ICU stays
  (e.g., a patient transferred out of the ICU and later readmitted).
""")

# Graphviz diagram showing the core hierarchy
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

    patient_tables [label="diagnoses_icd\\nprocedures_icd\\nprescriptions\\n..."];
    icu_tables [label="chartevents\\ninputevents\\noutputevents\\n..."];

    admissions -> patient_tables [style=dashed, label="hadm_id"];
    icustays -> icu_tables [style=dashed, label="{ICU_KEY}"];
}}
"""
st.graphviz_chart(dot)

# -- Join key matrix --

st.subheader("Join keys by table")

st.markdown(
    "This matrix shows which join keys each table contains. "
    "Two tables sharing a key can be joined on that key."
)

# Build display data
matrix_rows = []
for table_name, keys in sorted(table_keys.items()):
    matrix_rows.append(
        {
            "Table": table_name,
            "subject_id": "Y" if keys["subject_id"] else "",
            "hadm_id": "Y" if keys["hadm_id"] else "",
            ICU_KEY: "Y" if keys["icu_key"] else "",
        }
    )

st.dataframe(matrix_rows, width="stretch", hide_index=True)

# -- Grouped by connectivity level --

st.subheader("Tables grouped by connectivity")

# Categorize tables by which keys they have
patient_only = []
admission_level = []
icu_level = []
no_keys = []

for table_name, keys in sorted(table_keys.items()):
    if keys["icu_key"]:
        icu_level.append(table_name)
    elif keys["hadm_id"]:
        admission_level.append(table_name)
    elif keys["subject_id"]:
        patient_only.append(table_name)
    else:
        no_keys.append(table_name)

if icu_level:
    st.markdown(f"**ICU-level tables** (have `{ICU_KEY}`) -- one row per ICU event or measurement")
    st.markdown(", ".join(f"`{t}`" for t in icu_level))

if admission_level:
    st.markdown(
        "**Admission-level tables** (have `hadm_id`) "
        "-- one row per event within an admission"
    )
    st.markdown(", ".join(f"`{t}`" for t in admission_level))

if patient_only:
    st.markdown(
        "**Patient-level tables** (have `subject_id` only) "
        "-- one row per patient or per patient event"
    )
    st.markdown(", ".join(f"`{t}`" for t in patient_only))

if no_keys:
    st.markdown(
        "**Lookup/dictionary tables** (no join keys) "
        "-- reference data like ICD code descriptions"
    )
    st.markdown(", ".join(f"`{t}`" for t in no_keys))

# -- Practical guidance --

st.divider()
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
share a key. The join key matrix above tells you which key to use.
""")
