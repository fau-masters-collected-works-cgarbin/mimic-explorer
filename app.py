"""MIMIC Explorer -- Streamlit entry point with dataset selector and navigation."""

import streamlit as st

from mimic_explorer.config import DATASETS
from mimic_explorer.stats import compute_stats, load_stats, save_stats

st.set_page_config(page_title="MIMIC Explorer", page_icon="🏥", layout="wide")

# Navigation defined first, per Streamlit docs pattern
pages = st.navigation(
    [
        st.Page("pages/dataset_at_a_glance.py", title="Dataset at a Glance", icon="📊"),
        st.Page("pages/database_schema.py", title="Database Schema", icon="🔗"),
        st.Page("pages/clinical_insights.py", title="Clinical Insights", icon="🩺"),
        st.Page("pages/note_timeline.py", title="Clinical Timeline", icon="📋"),
        st.Page("pages/community_references.py", title="Community References", icon="📚"),
    ]
)

# Sidebar widgets after navigation -- pages read st.session_state["dataset_key"]
st.sidebar.selectbox(
    "Dataset",
    options=list(DATASETS.keys()),
    format_func=lambda k: DATASETS[k].name,
    key="dataset_key",
)
dataset_key = st.session_state["dataset_key"]
st.sidebar.caption(f"Path: `{DATASETS[dataset_key].base_path}`")

# Dataset stats: compute-once, save-to-disk cache for all static stats.
# Loaded once here and stashed in session_state so pages don't re-read from disk.
st.sidebar.divider()
_stats_key = f"cached_stats_{dataset_key}"
if _stats_key not in st.session_state:
    st.session_state[_stats_key] = load_stats(dataset_key)

if st.session_state[_stats_key]:
    st.sidebar.success("Dataset statistics cached", icon="✅")
    if st.sidebar.button("Recalculate statistics"):
        with st.spinner("Recalculating dataset statistics..."):
            st.session_state[_stats_key] = compute_stats(DATASETS[dataset_key])
            save_stats(dataset_key, st.session_state[_stats_key])
        st.rerun()
else:
    st.sidebar.info(
        "Dataset statistics have not been computed yet. "
        "This is a one-time operation that pre-computes all stats for both the "
        "Dataset at a Glance and Clinical Insights pages."
    )
    if st.sidebar.button("Compute dataset statistics"):
        with st.spinner("Computing dataset statistics (one-time)..."):
            st.session_state[_stats_key] = compute_stats(DATASETS[dataset_key])
            save_stats(dataset_key, st.session_state[_stats_key])
        st.rerun()

pages.run()
