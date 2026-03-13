"""Clinical Timeline -- notes and structured events across a hospital stay."""

import random
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from mimic_explorer.config import DATASETS
from mimic_explorer.db import get_connection, note_union_ref, resolve_refs

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

st.markdown(
    "Clinical notes and structured events across a hospital stay: "
    "where documentation clusters, where gaps appear, and how notes "
    "relate to lab results, unit transfers, and medication changes."
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

fig = px.bar(
    df_cats,
    x="count",
    y="category",
    orientation="h",
    labels={"count": "Notes", "category": ""},
)
fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=400)
st.plotly_chart(fig, width="stretch")

# ── Section 2: Admission Selector ──

st.subheader("Admission Timeline")

hadm_id_input = st.sidebar.text_input(
    "Admission ID (HADM_ID)", value=st.session_state.get("hadm_id_for_timeline", "")
)

if st.sidebar.button("Random admission", help="Pick a random admission with multiple notes"):

    @st.cache_data(show_spinner="Finding admissions with multiple notes...")
    def random_hadm_ids(ds):
        """Cache admissions with 3+ notes to avoid landing on single-note stays."""
        conn = get_connection()
        where_parts = [f'"{hadm_col}" IS NOT NULL']
        if error_filter:
            where_parts.append(error_filter)
        where = "WHERE " + " AND ".join(where_parts)
        return [
            row[0]
            for row in conn.execute(f"""
                SELECT "{hadm_col}" FROM (
                    SELECT "{hadm_col}"
                    FROM {noteevents_ref}
                    {where}
                    GROUP BY "{hadm_col}"
                    HAVING COUNT(*) >= 3
                ) USING SAMPLE 50
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
    result = conn.execute(
        f"""
        SELECT "{admit_col}"::TIMESTAMP AS admit, "{disch_col}"::TIMESTAMP AS disch
        FROM {admissions_ref}
        WHERE "{hadm_col}" = $1
    """,
        [hadm],
    ).fetchone()
    if not result:
        return None
    return {"admit": result[0], "disch": result[1]}


bounds = admission_bounds(dataset.name, hadm_id)
if not bounds:
    st.warning(f"No admission found for HADM_ID = {hadm_id}.")
    st.stop()


# ── Fetch notes and structured events in parallel ──

labevents_ref = refs["labevents"]
transfers_ref = refs["transfers"]
prescriptions_ref = refs["prescriptions"]


def _fetch_notes(hadm):
    conn = get_connection()
    cols = [
        f'"{row_id_col}"',
        f'"{category_col}"',
        f'"{description_col}"',
        f'"{charttime_col}"',
    ]
    if chartdate_col:
        cols.append(f'"{chartdate_col}"')
    where_parts = [f'"{hadm_col}" = $1']
    if error_filter:
        where_parts.append(error_filter)
    where = "WHERE " + " AND ".join(where_parts)
    if chartdate_col:
        order = f'COALESCE("{charttime_col}"::TIMESTAMP, "{chartdate_col}"::TIMESTAMP)'
    else:
        order = f'"{charttime_col}"::TIMESTAMP'
    return conn.execute(
        f"""
        SELECT {", ".join(cols)}
        FROM {noteevents_ref}
        {where}
        ORDER BY {order}
    """,
        [hadm],
    ).fetchdf()


def _fetch_abnormal_labs(hadm, ref):
    if ref is None:
        return pd.DataFrame()
    c = lab_cols
    conn = get_connection()
    return conn.execute(
        f"""
        SELECT "{c["charttime"]}"::TIMESTAMP AS timestamp,
               "{c["value"]}" AS value,
               "{c["valueuom"]}" AS unit,
               "{c["flag"]}" AS flag,
               CAST("{c["itemid"]}" AS VARCHAR) AS itemid
        FROM {ref}
        WHERE "{c["hadm"]}" = $1
          AND "{c["flag"]}" IS NOT NULL AND "{c["flag"]}" != ''
          AND "{c["charttime"]}" IS NOT NULL
        ORDER BY "{c["charttime"]}"
    """,
        [hadm],
    ).fetchdf()


def _fetch_transfers(hadm, ref):
    if ref is None:
        return pd.DataFrame()
    c = xfer_cols
    conn = get_connection()
    return conn.execute(
        f"""
        SELECT "{c["intime"]}"::TIMESTAMP AS timestamp,
               "{c["eventtype"]}" AS eventtype,
               "{c["careunit"]}" AS careunit
        FROM {ref}
        WHERE "{c["hadm"]}" = $1
          AND "{c["intime"]}" IS NOT NULL
        ORDER BY "{c["intime"]}"
    """,
        [hadm],
    ).fetchdf()


def _fetch_meds(hadm, ref):
    if ref is None:
        return pd.DataFrame()
    c = rx_cols
    conn = get_connection()
    return conn.execute(
        f"""
        SELECT "{c["starttime"]}"::TIMESTAMP AS start_time,
               "{c["stoptime"]}"::TIMESTAMP AS stop_time,
               "{c["drug"]}" AS drug
        FROM {ref}
        WHERE "{c["hadm"]}" = $1
          AND "{c["starttime"]}" IS NOT NULL
        ORDER BY "{c["starttime"]}"
    """,
        [hadm],
    ).fetchdf()


@st.cache_data(show_spinner="Loading admission data (first run may take ~10s)...")
def admission_data(ds, hadm, _lab_ref, _xfer_ref, _rx_ref):
    """Fetch notes and structured events in parallel (each thread gets its own connection)."""
    with ThreadPoolExecutor(max_workers=4) as pool:
        notes_future = pool.submit(_fetch_notes, hadm)
        lab_future = pool.submit(_fetch_abnormal_labs, hadm, _lab_ref)
        xfer_future = pool.submit(_fetch_transfers, hadm, _xfer_ref)
        med_future = pool.submit(_fetch_meds, hadm, _rx_ref)
    return {
        "notes": notes_future.result(),
        "labs": lab_future.result(),
        "transfers": xfer_future.result(),
        "meds": med_future.result(),
    }


data = admission_data(dataset.name, hadm_id, labevents_ref, transfers_ref, prescriptions_ref)
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
    height=max(250, 40 * n_rows),
    showlegend=True,
    legend_title_text="",
    xaxis_title="Hours from Admission",
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

# ── Section 3: Note Documentation Patterns ──

st.subheader("Note Documentation Patterns")
st.caption(
    "How notes are distributed over the stay and where documentation gaps occur. "
    "Structured events are not included here -- see the timeline above for the full picture."
)

if len(df_notes) < 3:
    st.caption(
        f"Too few notes for temporal density analysis ({len(df_notes)} note"
        f"{'s' if len(df_notes) != 1 else ''} in this admission). "
        "See the timeline above for the full picture of clinical activity."
    )
else:
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
        sorted_notes = df_notes.sort_values("timestamp")
        intervals = sorted_notes["timestamp"].diff().dt.total_seconds() / 3600
        intervals = intervals.dropna()

        # Position each gap at the midpoint between the two notes that define it
        hours = sorted_notes["hours_from_admit"].to_numpy()
        midpoints = (hours[:-1] + hours[1:]) / 2

        interval_df = pd.DataFrame(
            {
                "hours_from_admit": midpoints,
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

        fig_gap = go.Figure(go.Bar(x=interval_df["hours_from_admit"], y=interval_df["gap_hours"]))
        fig_gap.add_hline(y=12, line_dash="dot", line_color="orange", annotation_text="12h")
        fig_gap.update_layout(
            height=200,
            xaxis_title="Hours from Admission",
            yaxis_title="Gap (hours)",
            margin={"t": 10},
        )
        st.plotly_chart(fig_gap, width="stretch")
        st.caption(
            "Each bar is the time elapsed between two consecutive notes. "
            "Tall bars indicate documentation gaps; short bars indicate bursts of activity. "
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
    def fetch_note_text(ds, rid):
        conn = get_connection()
        result = conn.execute(
            f"""
            SELECT "{text_col}"
            FROM {noteevents_ref}
            WHERE CAST("{row_id_col}" AS VARCHAR) = $1
        """,
            [rid],
        ).fetchone()
        return result[0] if result else None

    text = fetch_note_text(dataset.name, selected_row_id)
    if text:
        st.text_area("Note content", value=text, height=400, disabled=True)
    else:
        st.warning("Could not retrieve note text.")
