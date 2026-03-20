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

# -- Demographics --

st.subheader("Demographics")

if "gender_dist" in stats and "race_dist" in stats:
    col1, col2 = st.columns(2)

    with col1:
        df_gender = pd.DataFrame(stats["gender_dist"])
        fig = px.pie(df_gender, values="count", names="gender", title="Gender (patient level)")
        fig.update_layout(height=300, margin={"t": 40, "b": 20})
        st.plotly_chart(fig, width="stretch")

    with col2:
        df_race = pd.DataFrame(stats["race_dist"])
        fig = px.pie(
            df_race,
            values="count",
            names="race",
            title="Race/ethnicity (admission level, top 15)",
        )
        fig.update_layout(height=300, margin={"t": 40, "b": 20})
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
    fig.update_layout(height=300, margin={"t": 40, "b": 30})
    st.plotly_chart(fig, width="stretch")

    if is_mimic3:
        st.caption(
            "Ages >89 are grouped at 90 due to HIPAA de-identification. "
            "Each bar counts admissions, not unique patients, so a patient "
            "readmitted at different ages contributes to multiple bars."
        )
    else:
        st.caption(
            "Anchor age is assigned once per patient at a reference year. "
            "Actual age at a specific admission may differ. "
            "The distribution skews younger than MIMIC-III because MIMIC-IV "
            "includes a broader population beyond ICU-only stays."
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
    fig.update_layout(height=300, margin={"t": 30, "b": 30})
    st.plotly_chart(fig, width="stretch")
    los_note = (
        "Capped at 60 days for readability. "
        f"The longest stay in this dataset is {df_los['los_days'].max():.0f} days."
    )
    if not is_mimic3:
        los_note += (
            " The spike near zero reflects ED visits and same-day discharges "
            "included in MIMIC-IV's broader admission scope."
        )
    st.caption(los_note)

# -- Per-admission volume --

if "per_admission_volume" in stats:
    st.subheader("Per-Admission Volume")
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

# -- Top diagnoses, procedures, labs (side by side) --

_top_n = 10
_top_sections = [
    ("top_diagnoses", "Top 10 Diagnoses", "diagnosis", "Admissions"),
    ("top_procedures", "Top 10 Procedures", "procedure", "Admissions"),
    ("top_labs", "Top 10 Lab Tests", "lab_test", "Measurements"),
]
_present = [(key, title, col, xlabel) for key, title, col, xlabel in _top_sections if key in stats]

if _present:
    cols = st.columns(len(_present))
    for col, (key, title, ycol, xlabel) in zip(cols, _present, strict=True):
        with col:
            st.subheader(title)
            df = pd.DataFrame(stats[key]).head(_top_n)
            fig = px.bar(
                df,
                x="count",
                y=ycol,
                orientation="h",
                labels={"count": xlabel, ycol: ""},
            )
            fig.update_layout(
                yaxis={"categoryorder": "total ascending"},
                height=400,
                margin={"t": 20, "b": 20, "l": 10, "r": 10},
            )
            st.plotly_chart(fig, width="stretch")

# -- Table sparsity --

if "table_coverage" in stats:
    st.subheader("Table Coverage")
    st.caption(
        "Not every admission has data in every table. This shows the percentage of "
        "admissions with at least one record in each clinical table. Low coverage "
        "means the table is only populated for certain types of stays."
    )
    coverage = stats["table_coverage"]
    df_all = pd.DataFrame([{"table": k, "pct": v} for k, v in coverage.items()])
    df_top = df_all.nlargest(10, "pct").sort_values("pct")
    df_bottom = df_all.nsmallest(10, "pct").sort_values("pct")

    col_top, col_bottom = st.columns(2)
    for col, df, title in [
        (col_top, df_top, "Highest coverage"),
        (col_bottom, df_bottom, "Lowest coverage"),
    ]:
        with col:
            fig = px.bar(
                df,
                x="pct",
                y="table",
                orientation="h",
                title=title,
                labels={"pct": "% of admissions", "table": ""},
                range_x=[0, 100],
            )
            fig.update_layout(
                height=max(200, len(df) * 35), margin={"t": 40, "b": 20, "l": 10, "r": 10}
            )
            st.plotly_chart(fig, width="stretch")

# -- Data quality --

if "data_quality" in stats:
    st.subheader("Data Quality Checks")
    df_dq = pd.DataFrame(stats["data_quality"]).rename(
        columns={"check": "Check", "count": "Count", "pct": "% of Total"}
    )
    st.dataframe(df_dq, hide_index=True, width=600)
