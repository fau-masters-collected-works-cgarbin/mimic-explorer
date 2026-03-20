"""Clinical Insights -- distributions and patterns in the dataset."""

import pandas as pd
import plotly.express as px
import streamlit as st

from mimic_explorer.config import DATASETS

st.title("Clinical Insights")

dataset = DATASETS[st.session_state["dataset_key"]]
st.caption(f"Showing: {dataset.name}")
is_mimic3 = dataset.uppercase_filenames

stats = st.session_state.get(f"cached_stats_{st.session_state['dataset_key']}")
if not stats:
    st.info("Click **Compute dataset statistics** in the sidebar to get started.")
    st.stop()

st.markdown(
    "Pre-built queries that reveal the shape of the data. "
    "All codes are joined against dictionary tables so you see "
    "names, not opaque IDs."
)

# -- Top diagnoses --

if "top_diagnoses" in stats:
    st.subheader("Top 20 Diagnoses")
    df_diag = pd.DataFrame(stats["top_diagnoses"])
    fig = px.bar(
        df_diag,
        x="count",
        y="diagnosis",
        orientation="h",
        labels={"count": "Admissions", "diagnosis": ""},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=500)
    st.plotly_chart(fig, width="stretch")

# -- Top procedures --

if "top_procedures" in stats:
    st.subheader("Top 20 Procedures")
    df_proc = pd.DataFrame(stats["top_procedures"])
    fig = px.bar(
        df_proc,
        x="count",
        y="procedure",
        orientation="h",
        labels={"count": "Admissions", "procedure": ""},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=500)
    st.plotly_chart(fig, width="stretch")

# -- Top lab tests --

if "top_labs" in stats:
    st.subheader("Top 20 Lab Tests")
    df_labs = pd.DataFrame(stats["top_labs"])
    fig = px.bar(
        df_labs,
        x="count",
        y="lab_test",
        orientation="h",
        labels={"count": "Measurements", "lab_test": ""},
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=500)
    st.plotly_chart(fig, width="stretch")

# -- Demographics --

st.subheader("Demographics")

if "gender_dist" in stats and "race_dist" in stats:
    col1, col2 = st.columns(2)

    with col1:
        df_gender = pd.DataFrame(stats["gender_dist"])
        fig = px.pie(df_gender, values="count", names="gender", title="Gender (patient level)")
        fig.update_layout(height=300)
        st.plotly_chart(fig, width="stretch")

    with col2:
        df_race = pd.DataFrame(stats["race_dist"])
        fig = px.pie(
            df_race,
            values="count",
            names="race",
            title="Race/ethnicity (admission level, top 15)",
        )
        fig.update_layout(height=300)
        st.plotly_chart(fig, width="stretch")

if "age_dist" in stats:
    df_age = pd.DataFrame(stats["age_dist"])
    fig = px.histogram(
        df_age,
        x="age",
        nbins=40,
        title="Age distribution at admission",
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

if "los_dist" in stats:
    st.subheader("Hospital Length of Stay")
    df_los = pd.DataFrame(stats["los_dist"])
    fig = px.histogram(
        df_los,
        x="los_days",
        nbins=100,
        labels={"los_days": "Length of Stay (days)", "count": "Admissions"},
        range_x=[0, 60],
    )
    fig.update_layout(height=350)
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Capped at 60 days for readability. "
        f"The longest stay in this dataset is {df_los['los_days'].max():.0f} days."
    )

# -- Per-admission volume --

if "per_admission_volume" in stats:
    st.subheader("Per-Admission Volume")
    st.markdown("How many records per hospital admission across key clinical tables.")
    rows = []
    for label, vol in stats["per_admission_volume"].items():
        rows.append(
            {
                "Table": label,
                "Median": vol["median"],
                "P25": vol["p25"],
                "P75": vol["p75"],
                "Max": vol["max"],
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width=600)

# -- Table sparsity --

if "table_sparsity" in stats:
    st.subheader("Table Sparsity")
    st.markdown("Percentage of admissions with at least one row in each clinical table.")
    sparsity = stats["table_sparsity"]
    df_sparse = pd.DataFrame(
        [{"table": k, "pct": v} for k, v in sorted(sparsity.items(), key=lambda x: x[1])]
    )
    fig = px.bar(
        df_sparse,
        x="pct",
        y="table",
        orientation="h",
        labels={"pct": "% of admissions", "table": ""},
        range_x=[0, 100],
    )
    fig.update_layout(height=max(250, len(sparsity) * 40))
    st.plotly_chart(fig, width="stretch")

# -- Data quality --

if "data_quality" in stats:
    st.subheader("Data Quality Checks")
    st.markdown("Counts of missing or empty values in key fields.")
    df_dq = pd.DataFrame(stats["data_quality"]).rename(
        columns={"check": "Check", "count": "Count", "pct": "% of Total"}
    )
    st.dataframe(df_dq, hide_index=True, width=600)
