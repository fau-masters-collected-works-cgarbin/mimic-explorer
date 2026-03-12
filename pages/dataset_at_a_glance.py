"""Dataset at a Glance -- key numbers that orient a new MIMIC user."""

import streamlit as st

from mimic_explorer.config import DATASETS
from mimic_explorer.db import get_connection, scalar_query, table_ref

st.title("Dataset at a Glance")

dataset = DATASETS[st.session_state["dataset_key"]]
st.caption(f"Showing: {dataset.name}")
tables = dataset.find_tables()
is_mimic3 = dataset.uppercase_filenames


def get_table(name):
    """Look up a table path by lowercase name, or None if missing."""
    return tables.get(name)


# Key table paths
patients_path = get_table("patients")
admissions_path = get_table("admissions")
icustays_path = get_table("icustays")

if not patients_path or not admissions_path:
    st.error("Could not find PATIENTS or ADMISSIONS tables in this dataset.")
    st.stop()


# -- Cached metric computation --


@st.cache_data(show_spinner="Computing dataset overview...")
def compute_overview(
    dataset_name: str,
    patients_path: str,
    admissions_path: str,
    icustays_path: str | None,
    *,
    uppercase: bool,
):
    """Compute all overview metrics in one pass per table."""
    conn = get_connection()
    p = table_ref(patients_path)
    a = table_ref(admissions_path)

    total_patients = scalar_query(conn, f"SELECT count(*) FROM {p}")
    total_admissions = scalar_query(conn, f"SELECT count(*) FROM {a}")

    # Gender split
    gender_col = "GENDER" if uppercase else "gender"
    male_pct = scalar_query(
        conn,
        f"SELECT round(100.0 * count(*) FILTER "
        f"(WHERE \"{gender_col}\" = 'M') / count(*), 1) FROM {p}",
    )

    # Admission date range
    admit_col = "ADMITTIME" if uppercase else "admittime"
    min_admit = scalar_query(conn, f'SELECT min("{admit_col}")::DATE FROM {a}')
    max_admit = scalar_query(conn, f'SELECT max("{admit_col}")::DATE FROM {a}')

    # Hospital mortality rate
    death_col = "HOSPITAL_EXPIRE_FLAG" if uppercase else "hospital_expire_flag"
    mortality_pct = scalar_query(
        conn,
        f'SELECT round(100.0 * avg("{death_col}"), 1) FROM {a}',
    )

    # Median hospital length of stay (days)
    disch_col = "DISCHTIME" if uppercase else "dischtime"
    median_los = scalar_query(
        conn,
        f"""SELECT round(median(
            date_diff('hour', "{admit_col}"::TIMESTAMP, "{disch_col}"::TIMESTAMP) / 24.0
        ), 1) FROM {a}""",
    )

    # ICU stats (if table exists)
    total_icu_stays = None
    median_icu_los = None
    if icustays_path:
        i = table_ref(icustays_path)
        total_icu_stays = scalar_query(conn, f"SELECT count(*) FROM {i}")
        los_col = "LOS" if uppercase else "los"
        median_icu_los = scalar_query(conn, f'SELECT round(median("{los_col}"), 1) FROM {i}')

    return {
        "total_patients": total_patients,
        "total_admissions": total_admissions,
        "male_pct": male_pct,
        "min_admit": min_admit,
        "max_admit": max_admit,
        "mortality_pct": mortality_pct,
        "median_los": median_los,
        "total_icu_stays": total_icu_stays,
        "median_icu_los": median_icu_los,
    }


metrics = compute_overview(
    dataset.name,
    str(patients_path),
    str(admissions_path),
    str(icustays_path) if icustays_path else None,
    uppercase=is_mimic3,
)

# -- Display --

st.markdown(
    "These numbers give you the shape of the dataset before you dive into individual tables."
)

# Row 1: Population
col1, col2, col3 = st.columns(3)
col1.metric("Patients", f"{metrics['total_patients']:,}")
col2.metric("Hospital Admissions", f"{metrics['total_admissions']:,}")
if metrics["total_icu_stays"]:
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
if metrics["median_icu_los"]:
    col3.metric("Median ICU Stay", f"{metrics['median_icu_los']} days")

# Contextual explanations for newcomers
st.divider()
st.subheader("What do these numbers mean?")

st.markdown(f"""
**{metrics['total_patients']:,} patients** had **{metrics['total_admissions']:,} hospital
admissions** between {metrics['min_admit']} and {metrics['max_admit']}. That's roughly
{metrics['total_admissions'] / metrics['total_patients']:.1f} admissions per patient on average,
meaning some patients were readmitted multiple times.

**Hospital mortality rate of {metrics['mortality_pct']}%** means this fraction of admissions ended
in death during the hospital stay. This is an ICU-centric dataset, so the mortality rate is higher
than a general hospital population.

**Median hospital stay of {metrics['median_los']} days** is the midpoint: half of all admissions
were shorter, half were longer. The median is more useful than the mean here because a few very long
stays would skew an average upward.
""")

if metrics["total_icu_stays"] and metrics["median_icu_los"]:
    st.markdown(f"""
**{metrics['total_icu_stays']:,} ICU stays** with a **median of {metrics['median_icu_los']} days**.
A single hospital admission can involve multiple ICU stays (e.g., a patient transferred out of the
ICU and later readmitted to it).
""")

st.info(
    "MIMIC contains de-identified data from Beth Israel Deaconess Medical Center. "
    "Dates are shifted randomly per patient (but preserved within each patient), "
    "so the date range above reflects shifted dates, not real calendar time."
)
