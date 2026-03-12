"""Schema Overview -- table list with row counts and column information."""

from pathlib import Path

import streamlit as st

from mimic_explorer.config import LARGE_TABLES, DatasetConfig
from mimic_explorer.db import column_info, get_connection, row_count

st.title("Schema Overview")

if "dataset" not in st.session_state:
    st.warning("Select a dataset from the main page first.")
    st.stop()

dataset: DatasetConfig = st.session_state["dataset"]
st.caption(f"Showing: {dataset.name}")
tables = dataset.find_tables()

# Table list with row counts
st.header("Tables")

include_large = st.checkbox(
    "Include large tables (CHARTEVENTS, LABEVENTS, etc.) -- slow first time",
    value=False,
)


@st.cache_data(show_spinner="Counting rows...")
def get_row_count(dataset_name: str, table_name: str, file_path_str: str) -> int | None:
    """Cached row count. Returns None if skipped."""
    if table_name in LARGE_TABLES:
        return None
    c = get_connection()
    return row_count(c, Path(file_path_str))


@st.cache_data(show_spinner="Reading columns...")
def get_column_info(dataset_name: str, file_path_str: str) -> list[dict[str, str]]:
    """Cached column info."""
    c = get_connection()
    return column_info(c, Path(file_path_str))


# Build table summary
rows_data = []
for table_name, file_path in sorted(tables.items()):
    if table_name in LARGE_TABLES and not include_large:
        count_display = "skipped (large)"
    else:
        count_val = get_row_count(dataset.name, table_name, str(file_path))
        count_display = "skipped (large)" if count_val is None else f"{count_val:,}"

    cols = get_column_info(dataset.name, str(file_path))
    col_names = ", ".join(c["name"] for c in cols)

    rows_data.append(
        {
            "Table": table_name,
            "Rows": count_display,
            "Columns": len(cols),
            "Column Names": col_names,
        }
    )

st.dataframe(rows_data, width="stretch", hide_index=True)

# Column detail for selected table
st.header("Column Details")
selected_table = st.selectbox("Select table", options=sorted(tables.keys()))

if selected_table:
    cols = get_column_info(dataset.name, str(tables[selected_table]))
    st.dataframe(cols, width="stretch", hide_index=True)
