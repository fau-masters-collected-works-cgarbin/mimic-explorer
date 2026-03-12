"""Temporal Note Timeline -- how clinical notes distribute across a hospital stay."""

import random

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from mimic_explorer.config import DATASETS
from mimic_explorer.db import get_connection, table_ref

st.title("Temporal Note Timeline")

dataset = DATASETS[st.session_state["dataset_key"]]
st.caption(f"Showing: {dataset.name}")
tables = dataset.find_tables()
is_mimic3 = dataset.uppercase_filenames


def get_table(name):
    path = tables.get(name)
    if path is None:
        return None
    return table_ref(path)


noteevents_ref = get_table("noteevents")
admissions_ref = get_table("admissions")

if not noteevents_ref:
    st.info(
        "This page requires clinical notes. MIMIC-III includes NOTEEVENTS; "
        "MIMIC-IV stores notes in a separate module (MIMIC-IV-Note) that "
        "is not currently configured."
    )
    st.stop()

if not admissions_ref:
    st.error("Could not find ADMISSIONS table in this dataset.")
    st.stop()

# Column name mappings
if is_mimic3:
    category_col = "CATEGORY"
    chartdate_col = "CHARTDATE"
    charttime_col = "CHARTTIME"
    hadm_col = "HADM_ID"
    row_id_col = "ROW_ID"
    iserror_col = "ISERROR"
    description_col = "DESCRIPTION"
    text_col = "TEXT"
    admit_col = "ADMITTIME"
    disch_col = "DISCHTIME"
else:
    # Placeholder for MIMIC-IV-Note -- column names TBD when module is added
    category_col = "category"
    chartdate_col = "chartdate"
    charttime_col = "charttime"
    hadm_col = "hadm_id"
    row_id_col = "note_id"
    iserror_col = None
    description_col = "note_type"
    text_col = "text"
    admit_col = "admittime"
    disch_col = "dischtime"

st.markdown(
    "How clinical notes distribute across a hospital stay. "
    "Relevant to temporal chunking and neighborhood expansion: "
    "where documentation clusters, where gaps appear, and what "
    "'nearby' means in practice."
)

# Error filter used in multiple queries
error_filter = f'("{iserror_col}" != \'1\' OR "{iserror_col}" IS NULL)' if iserror_col else None

# ── Section 1: Category Distribution ──

st.subheader("Note Categories")
st.caption("Distribution of note types across the entire dataset.")


@st.cache_data(show_spinner="Counting notes by category (first run may take ~10s)...")
def category_counts(ds):
    conn = get_connection()
    where = f"WHERE {error_filter}" if error_filter else ""
    return conn.execute(f"""
        SELECT "{category_col}" AS category, COUNT(*) AS count
        FROM {noteevents_ref}
        {where}
        GROUP BY "{category_col}"
        ORDER BY count DESC
    """).fetchdf()


df_cats = category_counts(dataset.name)
total_notes = int(df_cats["count"].sum())

fig = px.bar(
    df_cats,
    x="count",
    y="category",
    orientation="h",
    labels={"count": "Notes", "category": ""},
)
fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=400)
st.plotly_chart(fig, width="stretch")
st.caption(f"{total_notes:,} total notes across {len(df_cats)} categories.")

# ── Section 2: Admission Selector ──

st.divider()
st.subheader("Admission Timeline")

hadm_id_input = st.sidebar.text_input(
    "Admission ID (HADM_ID)", value=st.session_state.get("hadm_id_for_timeline", "")
)

if st.sidebar.button("Random admission", help="Pick a random admission that has notes"):

    @st.cache_data(show_spinner="Picking random admissions...")
    def random_hadm_ids(ds):
        """Cache a batch of random HADM_IDs to avoid repeated full scans."""
        conn = get_connection()
        where_parts = [f'"{hadm_col}" IS NOT NULL']
        if error_filter:
            where_parts.append(error_filter)
        where = "WHERE " + " AND ".join(where_parts)
        return [
            row[0]
            for row in conn.execute(f"""
                SELECT DISTINCT "{hadm_col}"
                FROM {noteevents_ref}
                {where}
                USING SAMPLE 50
            """).fetchall()
        ]

    candidates = random_hadm_ids(dataset.name)
    if candidates:
        st.session_state["hadm_id_for_timeline"] = str(random.choice(candidates))  # noqa: S311
        st.rerun()

# Category filter
category_filter = st.sidebar.multiselect(
    "Filter categories",
    options=df_cats["category"].tolist(),
    default=[],
    help="Leave empty to show all categories.",
)

if not hadm_id_input:
    st.info("Enter an admission ID in the sidebar, or click Random to pick one.")
    st.stop()

try:
    hadm_id = int(hadm_id_input)
except ValueError:
    st.error("HADM_ID must be a number.")
    st.stop()


# ── Fetch admission bounds ──


@st.cache_data(show_spinner="Fetching admission times...")
def admission_bounds(ds, hadm):
    conn = get_connection()
    result = conn.execute(f"""
        SELECT "{admit_col}"::TIMESTAMP AS admit, "{disch_col}"::TIMESTAMP AS disch
        FROM {admissions_ref}
        WHERE "{hadm_col}" = {hadm}
    """).fetchone()
    if not result:
        return None
    return {"admit": result[0], "disch": result[1]}


bounds = admission_bounds(dataset.name, hadm_id)
if not bounds:
    st.warning(f"No admission found for HADM_ID = {hadm_id}.")
    st.stop()


# ── Fetch notes metadata (no TEXT column) ──


@st.cache_data(show_spinner="Loading notes for this admission (first run may take ~10s)...")
def admission_notes(ds, hadm):
    conn = get_connection()
    cols = [
        f'"{row_id_col}"',
        f'"{category_col}"',
        f'"{description_col}"',
        f'"{chartdate_col}"',
        f'"{charttime_col}"',
    ]
    where_parts = [f'"{hadm_col}" = {hadm}']
    if error_filter:
        where_parts.append(error_filter)
    where = "WHERE " + " AND ".join(where_parts)
    return conn.execute(f"""
        SELECT {", ".join(cols)}
        FROM {noteevents_ref}
        {where}
        ORDER BY COALESCE("{charttime_col}"::TIMESTAMP, "{chartdate_col}"::TIMESTAMP)
    """).fetchdf()


df_notes = admission_notes(dataset.name, hadm_id)

if df_notes.empty:
    st.warning(f"No notes found for HADM_ID = {hadm_id}.")
    st.stop()

# Compute unified timestamp for each note
df_notes["timestamp"] = pd.to_datetime(
    df_notes[charttime_col].fillna(pd.to_datetime(df_notes[chartdate_col]).dt.strftime("%Y-%m-%d"))
)
df_notes["has_exact_time"] = df_notes[charttime_col].notna()

# Compute hours from admission
admit_ts = pd.Timestamp(bounds["admit"])
disch_ts = pd.Timestamp(bounds["disch"])
df_notes["hours_from_admit"] = (df_notes["timestamp"] - admit_ts).dt.total_seconds() / 3600

# Apply category filter if set
if category_filter:
    df_notes = df_notes[df_notes[category_col].isin(category_filter)]
    if df_notes.empty:
        st.warning("No notes match the selected categories for this admission.")
        st.stop()

los_hours = (disch_ts - admit_ts).total_seconds() / 3600

st.markdown(
    f"**Admission {hadm_id}**: {admit_ts:%Y-%m-%d %H:%M} to {disch_ts:%Y-%m-%d %H:%M} "
    f"({los_hours / 24:.1f} days). **{len(df_notes)} notes.**"
)

# ── Timeline scatter plot ──

fig = px.strip(
    df_notes,
    x="hours_from_admit",
    y=category_col,
    color=category_col,
    hover_data={
        description_col: True,
        "has_exact_time": True,
        "hours_from_admit": ":.1f",
        category_col: False,
    },
    labels={"hours_from_admit": "Hours from Admission", category_col: ""},
)

fig.add_vline(x=0, line_dash="dash", line_color="green", annotation_text="Admit")
fig.add_vline(x=los_hours, line_dash="dash", line_color="red", annotation_text="Discharge")

fig.update_layout(
    height=max(250, 80 * df_notes[category_col].nunique()),
    showlegend=False,
    xaxis_title="Hours from Admission",
)
st.plotly_chart(fig, width="stretch")
st.caption("Hover over points for details. Notes with date-only timestamps are placed at midnight.")

# ── Section 3: Temporal Density and Intervals ──

st.divider()
st.subheader("Temporal Density")

col_hist, col_intervals = st.columns(2)

with col_hist:
    st.markdown("**Notes per 6-hour block**")
    fig_hist = px.histogram(
        df_notes,
        x="hours_from_admit",
        nbins=max(4, int(los_hours / 6)),
        labels={"hours_from_admit": "Hours from Admission", "count": "Notes"},
    )
    fig_hist.update_layout(height=300)
    st.plotly_chart(fig_hist, width="stretch")

with col_intervals:
    st.markdown("**Note-to-note intervals**")
    if len(df_notes) >= 2:
        sorted_notes = df_notes.sort_values("timestamp")
        intervals = sorted_notes["timestamp"].diff().dt.total_seconds() / 3600
        intervals = intervals.dropna()

        interval_df = pd.DataFrame(
            {
                "note_pair": range(1, len(intervals) + 1),
                "gap_hours": intervals.to_numpy(),
            }
        )
        interval_df["gap_hours"] = interval_df["gap_hours"].round(1)

        median_gap = interval_df["gap_hours"].median()
        max_gap = interval_df["gap_hours"].max()
        long_gaps = int((interval_df["gap_hours"] > 12).sum())

        m1, m2, m3 = st.columns(3)
        m1.metric("Median gap", f"{median_gap:.1f}h")
        m2.metric("Longest gap", f"{max_gap:.1f}h")
        if long_gaps > 0:
            m3.metric("Gaps >12h", long_gaps)

        fig_gap = go.Figure(go.Bar(x=interval_df["note_pair"], y=interval_df["gap_hours"]))
        fig_gap.add_hline(y=12, line_dash="dot", line_color="orange", annotation_text="12h")
        fig_gap.update_layout(
            height=200,
            xaxis_title="Note pair",
            yaxis_title="Hours",
            margin={"t": 10},
        )
        st.plotly_chart(fig_gap, width="stretch")
    else:
        st.caption("Need at least 2 notes to compute intervals.")

st.caption(
    "Gaps longer than ~12 hours often correspond to overnight periods or weekends, "
    "natural boundaries for temporal chunking. Short, dense clusters typically align "
    "with clinical events (procedures, deterioration, rounds)."
)

# ── Section 4: Note Text Viewer ──

st.divider()
st.subheader("Note Text")

# Build a display label for each note
df_notes["label"] = (
    df_notes[row_id_col].astype(str)
    + " | "
    + df_notes[category_col]
    + " | "
    + df_notes["timestamp"].dt.strftime("%Y-%m-%d %H:%M")
    + df_notes["has_exact_time"].map({True: "", False: " (date only)"})
)

selected_label = st.selectbox("Select a note to read", options=df_notes["label"].tolist())

if selected_label:
    selected_row_id = int(selected_label.split(" | ")[0])

    @st.cache_data(show_spinner="Fetching note text...")
    def fetch_note_text(ds, rid):
        conn = get_connection()
        result = conn.execute(f"""
            SELECT "{text_col}"
            FROM {noteevents_ref}
            WHERE "{row_id_col}" = {rid}
        """).fetchone()
        return result[0] if result else None

    text = fetch_note_text(dataset.name, selected_row_id)
    if text:
        st.text_area("Note content", value=text, height=400, disabled=True)
    else:
        st.warning("Could not retrieve note text.")
