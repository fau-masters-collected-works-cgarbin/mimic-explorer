"""Clinical Timeline -- notes and structured events across a hospital stay."""

import random

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from mimic_explorer.config import DATASETS
from mimic_explorer.db import note_union_ref, resolve_refs
from mimic_explorer.timeline_queries import (
    fetch_admission_bounds,
    fetch_admission_data,
    fetch_category_counts,
    fetch_note_text,
    fetch_random_hadm_ids,
)

st.title("Clinical Timeline")

dataset = DATASETS[st.session_state["dataset_key"]]
st.caption(f"Showing: {dataset.name}")

# Clear stale HADM_ID when the user switches datasets
if st.session_state.get("_timeline_dataset") != st.session_state["dataset_key"]:
    st.session_state["_timeline_dataset"] = st.session_state["dataset_key"]
    st.session_state.pop("hadm_id_for_timeline", None)

tables = dataset.find_tables()
is_mimic3 = dataset.uppercase_filenames

refs = resolve_refs(tables, ["noteevents", "admissions", "labevents", "transfers", "prescriptions"])
admissions_ref = refs["admissions"]

if is_mimic3:
    noteevents_ref = refs["noteevents"]
else:
    note_tables = dataset.find_note_tables()
    noteevents_ref = note_union_ref(note_tables)

if not noteevents_ref:
    if is_mimic3:
        st.info(
            "This page requires the NOTEEVENTS table, which was not found "
            "in the MIMIC-III directory."
        )
    else:
        st.info(
            "This page requires MIMIC-IV-Note (a separate PhysioNet download). "
            "Set the MIMIC_IV_NOTE_PATH environment variable to the directory "
            "containing discharge.csv.gz and radiology.csv.gz, then restart the app."
        )
    st.stop()

if not admissions_ref:
    st.error("Could not find ADMISSIONS table in this dataset.")
    st.stop()

# Column names
category_col = dataset.col("category")
chartdate_col = dataset.col("chartdate")
charttime_col = dataset.col("charttime")
hadm_col = dataset.col("hadm_id")
row_id_col = dataset.col("note_id")
iserror_col = dataset.col("iserror")
description_col = dataset.col("note_type")
text_col = dataset.col("text")
admit_col = dataset.col("admittime")
disch_col = dataset.col("dischtime")

# Structured event columns grouped by table for use in per-admission queries
lab_cols = {
    "charttime": dataset.col("charttime"),
    "flag": dataset.col("flag"),
    "itemid": dataset.col("itemid"),
    "hadm": dataset.col("hadm_id"),
    "value": dataset.col("value"),
    "valueuom": dataset.col("valueuom"),
}
xfer_cols = {
    "intime": dataset.col("intime"),
    "eventtype": dataset.col("eventtype"),
    "careunit": dataset.col("careunit"),
    "hadm": dataset.col("hadm_id"),
}
rx_cols = {
    "starttime": dataset.col("rx_starttime"),
    "stoptime": dataset.col("rx_stoptime"),
    "drug": dataset.col("drug"),
    "hadm": dataset.col("hadm_id"),
}

# Parameters for _fetch_notes (passed via fetch_admission_data)
note_cols = {
    "row_id_col": row_id_col,
    "category_col": category_col,
    "description_col": description_col,
    "charttime_col": charttime_col,
    "chartdate_col": chartdate_col,
    "hadm_col": hadm_col,
    "error_filter": (
        f'("{iserror_col}" != \'1\' OR "{iserror_col}" IS NULL)' if iserror_col else None
    ),
}
error_filter = note_cols["error_filter"]

st.markdown(
    "Clinical notes and structured events across a hospital stay: "
    "where documentation clusters, where gaps appear, and how notes "
    "relate to lab results, unit transfers, and medication changes."
)

# ── Section 1: Category Distribution ──

st.subheader("Note Categories")
st.caption("Distribution of note types across the entire dataset.")


@st.cache_data(show_spinner="Counting notes by category (first run may take ~10s)...")
def _cached_category_counts(ds):
    return fetch_category_counts(noteevents_ref, category_col, error_filter)


df_cats = _cached_category_counts(dataset.name)

fig = px.bar(
    df_cats,
    x="count",
    y="category",
    orientation="h",
    labels={"count": "Notes", "category": ""},
)
bar_height = min(max(len(df_cats) * 30, 120), 400)
fig.update_layout(
    yaxis={"categoryorder": "total ascending"}, height=bar_height, margin={"t": 10, "b": 10}
)
st.plotly_chart(fig, width="stretch")

# ── Section 2: Admission Selector ──

st.subheader("Admission Timeline")

hadm_id_input = st.sidebar.text_input(
    "Admission ID (HADM_ID)", value=st.session_state.get("hadm_id_for_timeline", "")
)

if st.sidebar.button("Random admission", help="Pick a random admission with multiple notes"):

    @st.cache_data(show_spinner="Finding admissions with multiple notes...")
    def _cached_random_hadm_ids(ds):
        return fetch_random_hadm_ids(noteevents_ref, hadm_col, error_filter)

    candidates = _cached_random_hadm_ids(dataset.name)
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
def _cached_admission_bounds(ds, hadm):
    return fetch_admission_bounds(admissions_ref, hadm, hadm_col, admit_col, disch_col)


bounds = _cached_admission_bounds(dataset.name, hadm_id)
if not bounds:
    st.warning(f"No admission found for HADM_ID = {hadm_id}.")
    st.stop()


# ── Fetch notes and structured events in parallel ──

labevents_ref = refs["labevents"]
transfers_ref = refs["transfers"]
prescriptions_ref = refs["prescriptions"]


@st.cache_data(show_spinner="Loading admission data (first run may take ~10s)...")
def _cached_admission_data(ds, hadm, _lab_ref, _xfer_ref, _rx_ref):
    return fetch_admission_data(
        hadm,
        noteevents_ref,
        _lab_ref,
        _xfer_ref,
        _rx_ref,
        note_cols=note_cols,
        lab_cols=lab_cols,
        xfer_cols=xfer_cols,
        rx_cols=rx_cols,
    )


data = _cached_admission_data(
    dataset.name, hadm_id, labevents_ref, transfers_ref, prescriptions_ref
)
df_notes = data["notes"]
df_labs = data["labs"]
df_transfers = data["transfers"]
df_meds = data["meds"]

if df_notes.empty:
    st.warning(f"No notes found for HADM_ID = {hadm_id}.")
    st.stop()

# Compute unified timestamp for each note: use CHARTTIME when available, fall back to CHARTDATE
if chartdate_col:
    df_notes["timestamp"] = pd.to_datetime(
        df_notes[charttime_col], format="mixed", errors="coerce"
    ).fillna(pd.to_datetime(df_notes[chartdate_col], format="mixed", errors="coerce"))
    df_notes["has_exact_time"] = df_notes[charttime_col].notna()
else:
    df_notes["timestamp"] = pd.to_datetime(df_notes[charttime_col], format="mixed", errors="coerce")
    df_notes["has_exact_time"] = True

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

# Build event summary line
event_parts = []
if not df_labs.empty:
    event_parts.append(f"{len(df_labs)} abnormal labs")
if not df_transfers.empty:
    event_parts.append(f"{len(df_transfers)} transfers")
if not df_meds.empty:
    event_parts.append(f"{len(df_meds)} medication orders")
if event_parts:
    st.caption(f"Structured events: {', '.join(event_parts)}.")

# ── Timeline scatter plot ──

# Build a detailed y-axis label: "Category / Description" when description adds info
df_notes["timeline_label"] = df_notes.apply(
    lambda r: (
        f"{r[category_col]} / {r[description_col]}"
        if pd.notna(r[description_col]) and r[description_col] != r[category_col]
        else r[category_col]
    ),
    axis=1,
)

# Map has_exact_time to a label for the legend
df_notes["precision"] = df_notes["has_exact_time"].map(
    {True: "Exact time", False: "Date only (midnight)"}
)

fig = px.scatter(
    df_notes,
    x="hours_from_admit",
    y="timeline_label",
    color="timeline_label",
    symbol="precision",
    symbol_map={"Exact time": "circle", "Date only (midnight)": "diamond-open"},
    hover_data={
        description_col: True,
        "precision": True,
        "hours_from_admit": ":.1f",
        category_col: False,
    },
    labels={"hours_from_admit": "Hours from Admission", "timeline_label": ""},
)

# Overlay structured clinical events on the timeline
if not df_labs.empty:
    lab_hours = (pd.to_datetime(df_labs["timestamp"]) - admit_ts).dt.total_seconds() / 3600
    fig.add_trace(
        go.Scatter(
            x=lab_hours,
            y=["Abnormal lab"] * len(lab_hours),
            mode="markers",
            marker={"symbol": "triangle-up", "size": 7, "color": "#d62728"},
            name="Abnormal lab",
            hovertext=(
                df_labs["flag"].astype(str)
                + ": "
                + df_labs["value"].astype(str)
                + " "
                + df_labs["unit"].fillna("").astype(str)
            ),
            hoverinfo="text+x",
        )
    )

if not df_transfers.empty:
    xfer_hours = (pd.to_datetime(df_transfers["timestamp"]) - admit_ts).dt.total_seconds() / 3600
    xfer_labels = (
        df_transfers["eventtype"].fillna("") + " \u2192 " + df_transfers["careunit"].fillna("")
    )
    fig.add_trace(
        go.Scatter(
            x=xfer_hours,
            y=["Transfer"] * len(xfer_hours),
            mode="markers",
            marker={"symbol": "square", "size": 9, "color": "#2ca02c"},
            name="Transfer",
            hovertext=xfer_labels,
            hoverinfo="text+x",
        )
    )

if not df_meds.empty:
    med_hours = (pd.to_datetime(df_meds["start_time"]) - admit_ts).dt.total_seconds() / 3600
    fig.add_trace(
        go.Scatter(
            x=med_hours,
            y=["Medication start"] * len(med_hours),
            mode="markers",
            marker={"symbol": "diamond", "size": 7, "color": "#9467bd"},
            name="Medication start",
            hovertext=df_meds["drug"],
            hoverinfo="text+x",
        )
    )

fig.add_vline(x=0, line_dash="dash", line_color="green", annotation_text="Admit")
fig.add_vline(x=los_hours, line_dash="dash", line_color="red", annotation_text="Discharge")

# Count all unique y-axis labels including event rows
n_rows = df_notes["timeline_label"].nunique()
if not df_labs.empty:
    n_rows += 1
if not df_transfers.empty:
    n_rows += 1
if not df_meds.empty:
    n_rows += 1

fig.update_layout(
    height=max(200, 30 * n_rows),
    showlegend=True,
    legend_title_text="",
    xaxis_title="Hours from Admission",
    margin={"t": 20, "b": 10},
)
# Hide color legend entries for note categories (redundant with y-axis),
# keep symbol entries and structured event entries
for trace in fig.data:
    if hasattr(trace, "marker") and trace.marker.symbol in (None, "circle"):
        trace.showlegend = False
st.plotly_chart(fig, width="stretch")
caption_parts = [
    "Notes with date-only timestamps (diamonds) are placed at midnight, "
    "which can make same-day notes appear before the recorded admission time.",
    "Structured events (labs, transfers, medications) are shown as distinct marker types.",
]
if is_mimic3:
    caption_parts.append(
        "MIMIC-III medication times are date-only (no time of day), "
        "so medication markers also appear at midnight."
    )
st.caption(" ".join(caption_parts))

# ── Section 3: Note-to-note intervals ──

if len(df_notes) < 3:
    st.caption(
        f"Too few notes for interval analysis ({len(df_notes)} note"
        f"{'s' if len(df_notes) != 1 else ''})."
    )
else:
    st.markdown("**Note-to-note intervals**")
    sorted_notes = df_notes.sort_values("timestamp")
    intervals = sorted_notes["timestamp"].diff().dt.total_seconds() / 3600
    intervals = intervals.dropna()

    # Position each gap at the second note (when documentation resumed)
    hours = sorted_notes["hours_from_admit"].to_numpy()

    interval_df = pd.DataFrame(
        {
            "hours_from_admit": hours[1:],
            "gap_hours": intervals.to_numpy(),
        }
    )
    interval_df["gap_hours"] = interval_df["gap_hours"].round(1)

    median_gap = interval_df["gap_hours"].median()
    max_gap = interval_df["gap_hours"].max()
    long_gaps = int((interval_df["gap_hours"] > 12).sum())

    gaps_text = f"Median gap: {median_gap:.1f}h · Longest gap: {max_gap:.1f}h"
    if long_gaps > 0:
        gaps_text += f" · Gaps >12h: {long_gaps}"
    st.caption(gaps_text)

    fig_gap = go.Figure()
    fig_gap.add_trace(
        go.Scatter(
            x=interval_df["hours_from_admit"],
            y=interval_df["gap_hours"],
            mode="markers",
            marker={"size": 7, "color": "#636EFA"},
            hovertemplate="Hour %{x:.1f}<br>Gap: %{y:.1f}h<extra></extra>",
        )
    )
    # Stems: vertical lines from baseline to each marker
    for _, row in interval_df.iterrows():
        fig_gap.add_shape(
            type="line",
            x0=row["hours_from_admit"],
            x1=row["hours_from_admit"],
            y0=0,
            y1=row["gap_hours"],
            line={"color": "#636EFA", "width": 2},
        )
    fig_gap.add_hline(y=12, line_dash="dot", line_color="orange", annotation_text="12h")
    fig_gap.update_layout(
        height=200,
        xaxis_title="Hours from Admission",
        yaxis_title="Gap (hours)",
        margin={"t": 10, "b": 10},
    )
    st.plotly_chart(fig_gap, width="stretch")
    st.caption(
        "Each stem shows the time elapsed since the previous note. "
        "Tall stems indicate documentation gaps; short ones indicate bursts of activity. "
        "Gaps above the 12h line often align with overnight periods or weekends."
    )

# ── Section 4: Note Text Viewer ──

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
    selected_row_id = selected_label.split(" | ")[0]

    @st.cache_data(show_spinner="Fetching note text...")
    def _cached_note_text(ds, rid):
        return fetch_note_text(noteevents_ref, rid, text_col, row_id_col)

    text = _cached_note_text(dataset.name, selected_row_id)
    if text:
        st.text_area("Note content", value=text, height=400, disabled=True)
    else:
        st.warning("Could not retrieve note text.")
