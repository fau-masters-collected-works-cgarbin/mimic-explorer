"""Dataset at a Glance: key numbers that orient a new MIMIC user."""

import streamlit as st

from mimic_explorer.config import DATASETS

st.title("Dataset at a Glance")

dataset = DATASETS[st.session_state["dataset_key"]]
st.caption(f"Showing: {dataset.name}")

stats = st.session_state.get(f"cached_stats_{st.session_state['dataset_key']}")
if not stats or "overview" not in stats:
    st.info("Click **Compute dataset statistics** in the sidebar to get started.")
    st.stop()

metrics = stats["overview"]
if not metrics:
    st.error("Could not find PATIENTS or ADMISSIONS tables in this dataset.")
    st.stop()

# -- Display --

st.markdown(
    "These numbers give you the shape of the dataset before you dive into individual tables."
)

# Row 1: Population
col1, col2, col3 = st.columns(3)
col1.metric("Patients", f"{metrics['total_patients']:,}")
col2.metric("Hospital Admissions", f"{metrics['total_admissions']:,}")
if metrics["total_icu_stays"] is not None:
    col3.metric("ICU Stays", f"{metrics['total_icu_stays']:,}")

# Row 2: Key rates
col1, col2, col3 = st.columns(3)
col1.metric("Male Patients", f"{metrics['male_pct']}%")
col2.metric("Hospital Mortality Rate", f"{metrics['mortality_pct']}%")
col3.metric(
    "Admissions per Patient",
    f"{metrics['total_admissions'] / metrics['total_patients']:.1f}",
)

# Row 3: Time and LOS
col1, col2, col3 = st.columns(3)
col1.metric("Date Range", f"{metrics['min_admit']} to {metrics['max_admit']}")
col2.metric("Median Hospital Stay", f"{metrics['median_los']} days")
if metrics["median_icu_los"] is not None:
    col3.metric("Median ICU Stay", f"{metrics['median_icu_los']} days")

# Contextual explanations for newcomers
st.divider()
st.subheader("What do these numbers mean?")

st.markdown(f"""
**{metrics["total_patients"]:,} patients** had **{metrics["total_admissions"]:,} hospital
admissions** between {metrics["min_admit"]} and {metrics["max_admit"]}. That's roughly
{metrics["total_admissions"] / metrics["total_patients"]:.1f} admissions per patient on average,
meaning some patients were readmitted multiple times.

**Hospital mortality rate of {metrics["mortality_pct"]}%** means this fraction of admissions ended
in death during the hospital stay. This is an ICU-centric dataset, so the mortality rate is higher
than a general hospital population.

**Median hospital stay of {metrics["median_los"]} days** is the midpoint: half of all admissions
were shorter, half were longer. The median is more useful than the mean here because a few very long
stays would skew an average upward.
""")

if metrics["total_icu_stays"] is not None and metrics["median_icu_los"] is not None:
    st.markdown(f"""
**{metrics["total_icu_stays"]:,} ICU stays** with a **median of {metrics["median_icu_los"]} days**.
A single hospital admission can involve multiple ICU stays (e.g., a patient transferred out of the
ICU and later readmitted to it).
""")

st.info(
    "MIMIC contains de-identified data from Beth Israel Deaconess Medical Center. "
    "Dates are shifted randomly per patient (but preserved within each patient), "
    "so the date range above reflects shifted dates, not real calendar time."
)
