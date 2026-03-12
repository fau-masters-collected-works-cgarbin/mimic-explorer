"""Clinical Insights -- distributions and patterns in the dataset."""

import plotly.express as px
import streamlit as st

from mimic_explorer.config import DATASETS
from mimic_explorer.db import get_connection, table_ref

st.title("Clinical Insights")

dataset = DATASETS[st.session_state["dataset_key"]]
st.caption(f"Showing: {dataset.name}")
tables = dataset.find_tables()
is_mimic3 = dataset.uppercase_filenames

st.markdown(
    "Pre-built queries that reveal the shape of the data. "
    "All codes are joined against dictionary tables so you see "
    "names, not opaque IDs."
)


def get_table(name):
    path = tables.get(name)
    if path is None:
        return None
    return table_ref(path)


# Resolve table references
patients_ref = get_table("patients")
admissions_ref = get_table("admissions")
diagnoses_ref = get_table("diagnoses_icd")
procedures_ref = get_table("procedures_icd")
d_diag_ref = get_table("d_icd_diagnoses")
d_proc_ref = get_table("d_icd_procedures")
d_lab_ref = get_table("d_labitems")
labevents_ref = get_table("labevents")

# Column name mappings
if is_mimic3:
    icd_col = "ICD9_CODE"
    icd_join = f'd."{icd_col}" = t."{icd_col}"'
    title_col = "LONG_TITLE"
    gender_col = "GENDER"
    admit_col = "ADMITTIME"
    disch_col = "DISCHTIME"
    race_col = "ETHNICITY"
    itemid_col = "ITEMID"
    label_col = "LABEL"
else:
    icd_col = "icd_code"
    icd_join = f'd."{icd_col}" = t."{icd_col}" AND d."icd_version" = t."icd_version"'
    title_col = "long_title"
    gender_col = "gender"
    admit_col = "admittime"
    disch_col = "dischtime"
    race_col = "race"
    itemid_col = "itemid"
    label_col = "label"


# -- Top diagnoses --

if diagnoses_ref and d_diag_ref:
    st.subheader("Top 20 Diagnoses")
    st.caption("Most frequently assigned diagnosis codes across all admissions.")

    @st.cache_data(show_spinner="Querying diagnoses...")
    def top_diagnoses(ds):
        conn = get_connection()
        return conn.execute(f"""
            SELECT d."{title_col}" AS diagnosis, count(*) AS count
            FROM {diagnoses_ref} t
            JOIN {d_diag_ref} d ON {icd_join}
            GROUP BY d."{title_col}"
            ORDER BY count DESC
            LIMIT 20
        """).fetchdf()

    df_diag = top_diagnoses(dataset.name)
    fig = px.bar(
        df_diag, x="count", y="diagnosis", orientation="h",
        labels={"count": "Admissions", "diagnosis": ""},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=500)
    st.plotly_chart(fig, width="stretch")

# -- Top procedures --

if procedures_ref and d_proc_ref:
    st.subheader("Top 20 Procedures")
    st.caption("Most frequently recorded procedure codes across all admissions.")

    @st.cache_data(show_spinner="Querying procedures...")
    def top_procedures(ds):
        conn = get_connection()
        return conn.execute(f"""
            SELECT d."{title_col}" AS procedure, count(*) AS count
            FROM {procedures_ref} t
            JOIN {d_proc_ref} d ON {icd_join}
            GROUP BY d."{title_col}"
            ORDER BY count DESC
            LIMIT 20
        """).fetchdf()

    df_proc = top_procedures(dataset.name)
    fig = px.bar(
        df_proc, x="count", y="procedure", orientation="h",
        labels={"count": "Admissions", "procedure": ""},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=500)
    st.plotly_chart(fig, width="stretch")

# -- Top lab tests --

if labevents_ref and d_lab_ref:
    st.subheader("Top 20 Lab Tests")
    st.caption(
        "Most frequently ordered lab tests. Based on a sample of the first "
        "1 million rows (labevents is very large)."
    )

    @st.cache_data(show_spinner="Sampling lab events (this may take a moment)...")
    def top_labs(ds):
        conn = get_connection()
        return conn.execute(f"""
            SELECT d."{label_col}" AS lab_test, count(*) AS count
            FROM (SELECT "{itemid_col}" FROM {labevents_ref} LIMIT 1000000) t
            JOIN {d_lab_ref} d ON d."{itemid_col}" = t."{itemid_col}"
            GROUP BY d."{label_col}"
            ORDER BY count DESC
            LIMIT 20
        """).fetchdf()

    df_labs = top_labs(dataset.name)
    fig = px.bar(
        df_labs, x="count", y="lab_test", orientation="h",
        labels={"count": "Measurements (sampled)", "lab_test": ""},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=500)
    st.plotly_chart(fig, width="stretch")

# -- Demographics --

st.subheader("Demographics")

if patients_ref and admissions_ref:
    col1, col2 = st.columns(2)

    # Gender distribution
    @st.cache_data(show_spinner="Computing gender distribution...")
    def gender_dist(ds):
        conn = get_connection()
        return conn.execute(f"""
            SELECT "{gender_col}" AS gender, count(*) AS count
            FROM {patients_ref}
            GROUP BY "{gender_col}"
            ORDER BY count DESC
        """).fetchdf()

    with col1:
        st.markdown("**Gender distribution** (patient level)")
        df_gender = gender_dist(dataset.name)
        fig = px.pie(df_gender, values="count", names="gender")
        fig.update_layout(height=300)
        st.plotly_chart(fig, width="stretch")

    # Race/ethnicity distribution
    @st.cache_data(show_spinner="Computing race/ethnicity distribution...")
    def race_dist(ds):
        conn = get_connection()
        return conn.execute(f"""
            SELECT "{race_col}" AS race, count(*) AS count
            FROM {admissions_ref}
            GROUP BY "{race_col}"
            ORDER BY count DESC
            LIMIT 15
        """).fetchdf()

    with col2:
        st.markdown("**Race/ethnicity distribution** (admission level, top 15)")
        df_race = race_dist(dataset.name)
        fig = px.pie(df_race, values="count", names="race")
        fig.update_layout(height=300)
        st.plotly_chart(fig, width="stretch")

    # Age distribution
    st.markdown("**Age distribution at admission**")

    @st.cache_data(show_spinner="Computing age distribution...")
    def age_dist(ds):
        conn = get_connection()
        if is_mimic3:
            # MIMIC-III: compute age from DOB and first admission time.
            # Patients >89 have DOB shifted to ~300 years before admission;
            # cap at 90 to represent the ">89" group.
            return conn.execute(f"""
                SELECT
                    LEAST(
                        date_diff('year', "DOB"::TIMESTAMP, "ADMITTIME"::TIMESTAMP),
                        90
                    ) AS age
                FROM {patients_ref} p
                JOIN {admissions_ref} a ON p."SUBJECT_ID" = a."SUBJECT_ID"
            """).fetchdf()
        # MIMIC-IV: anchor_age is directly available (one per patient)
        return conn.execute(f"""
                SELECT "anchor_age" AS age
                FROM {patients_ref}
            """).fetchdf()

    df_age = age_dist(dataset.name)
    fig = px.histogram(
        df_age, x="age", nbins=40,
        labels={"age": "Age (years)", "count": "Count"},
    )
    fig.update_layout(height=350)
    st.plotly_chart(fig, width="stretch")

    if is_mimic3:
        st.caption(
            "Ages >89 are grouped at 90 due to HIPAA de-identification. "
            "Age is computed per admission, so patients with multiple "
            "admissions appear multiple times."
        )
    else:
        st.caption(
            "Anchor age is assigned once per patient at a reference year. "
            "Actual age at a specific admission may differ."
        )

# -- Length of stay distribution --

if admissions_ref:
    st.subheader("Hospital Length of Stay")

    @st.cache_data(show_spinner="Computing length-of-stay distribution...")
    def los_dist(ds):
        conn = get_connection()
        return conn.execute(f"""
            SELECT
                date_diff('hour',
                    "{admit_col}"::TIMESTAMP,
                    "{disch_col}"::TIMESTAMP
                ) / 24.0 AS los_days
            FROM {admissions_ref}
            WHERE "{disch_col}" IS NOT NULL
        """).fetchdf()

    df_los = los_dist(dataset.name)
    fig = px.histogram(
        df_los, x="los_days", nbins=100,
        labels={"los_days": "Length of Stay (days)", "count": "Admissions"},
        range_x=[0, 60],
    )
    fig.update_layout(height=350)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Capped at 60 days for readability. "
        f"The longest stay in this dataset is {df_los['los_days'].max():.0f} days."
    )
