"""MIMIC Explorer -- Streamlit entry point with dataset selector and navigation."""

import streamlit as st

from mimic_explorer.config import DATASETS

st.set_page_config(page_title="MIMIC Explorer", page_icon="🏥", layout="wide")

# Dataset selector in sidebar
dataset_key = st.sidebar.selectbox(
    "Dataset",
    options=list(DATASETS.keys()),
    format_func=lambda k: DATASETS[k].name,
)

dataset = DATASETS[dataset_key]

# Validate that the data path exists
if not dataset.base_path.exists():
    st.error(f"Data path not found: `{dataset.base_path}`")
    st.info("Update the paths in `src/mimic_explorer/config.py` to match your local setup.")
    st.stop()

# Store in session state for pages to access
st.session_state["dataset_key"] = dataset_key
st.session_state["dataset"] = dataset

# Define page order explicitly -- no numeric prefixes needed
pages = st.navigation(
    [
        st.Page("pages/dataset_at_a_glance.py", title="Dataset at a Glance", icon="📊"),
        st.Page("pages/table_relationships.py", title="Table Relationships", icon="🔗"),
        st.Page("pages/clinical_insights.py", title="Clinical Insights", icon="🩺"),
        st.Page("pages/schema_overview.py", title="Schema Overview", icon="📋"),
        st.Page("pages/table_browser.py", title="Table Browser", icon="🔍"),
    ]
)

pages.run()
