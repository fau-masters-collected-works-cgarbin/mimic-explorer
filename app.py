"""MIMIC Explorer -- Streamlit entry point with dataset selector and navigation."""

import streamlit as st

from mimic_explorer.config import DATASETS

st.set_page_config(page_title="MIMIC Explorer", page_icon="🏥", layout="wide")

# Navigation defined first, per Streamlit docs pattern
pages = st.navigation(
    [
        st.Page("pages/dataset_at_a_glance.py", title="Dataset at a Glance", icon="📊"),
        st.Page("pages/database_schema.py", title="Database Schema", icon="🔗"),
        st.Page("pages/clinical_insights.py", title="Clinical Insights", icon="🩺"),
        st.Page("pages/note_timeline.py", title="Temporal Note Timeline", icon="📝"),
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

pages.run()
