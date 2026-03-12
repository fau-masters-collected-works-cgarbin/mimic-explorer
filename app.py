"""MIMIC Explorer -- Streamlit entry point with dataset selector."""

import streamlit as st

from mimic_explorer.config import DATASETS

st.set_page_config(page_title="MIMIC Explorer", page_icon="🏥", layout="wide")

st.title("MIMIC Explorer")

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

st.markdown(f"**Active dataset:** {dataset.name}")
st.markdown(f"**Data path:** `{dataset.base_path}`")

tables = dataset.find_tables()
st.markdown(f"**Tables found:** {len(tables)}")

st.divider()
st.markdown("Use the sidebar to navigate to different pages.")
