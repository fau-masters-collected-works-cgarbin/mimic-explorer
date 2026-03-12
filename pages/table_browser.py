"""Table Browser -- sample rows, column stats, filter and sort."""

from pathlib import Path

import streamlit as st

from mimic_explorer.config import LARGE_TABLES, DatasetConfig
from mimic_explorer.db import get_connection, table_ref

st.title("Table Browser")

if "dataset" not in st.session_state:
    st.warning("Select a dataset from the main page first.")
    st.stop()

dataset: DatasetConfig = st.session_state["dataset"]
tables = dataset.find_tables()
conn = get_connection()

# Table selector
selected_table = st.sidebar.selectbox("Table", options=sorted(tables.keys()))

if not selected_table:
    st.stop()

file_path = tables[selected_table]
ref = table_ref(file_path)

if selected_table in LARGE_TABLES:
    st.warning(f"`{selected_table}` is very large. Queries may take a while on first run.")


# Column info (cached)
@st.cache_data(show_spinner="Reading schema...")
def get_columns(dataset_name: str, table_name: str, file_path_str: str):
    c = get_connection()
    cursor = c.execute(f"SELECT * FROM read_csv_auto('{file_path_str}') LIMIT 0")
    return [{"name": col[0], "type": str(col[1])} for col in cursor.description]


columns = get_columns(dataset.name, selected_table, str(file_path))
col_names = [c["name"] for c in columns]

# Filters
st.sidebar.subheader("Filters")
where_clauses = []
for col in columns[:10]:  # Show filter inputs for the first 10 columns only
    val = st.sidebar.text_input(f"{col['name']} =", key=f"filter_{col['name']}")
    if val:
        # Simple equality filter -- quote strings
        if col["type"] in ("BIGINT", "INTEGER", "DOUBLE", "FLOAT", "DECIMAL"):
            where_clauses.append(f'"{col["name"]}" = {val}')
        else:
            where_clauses.append(f"\"{col['name']}\" = '{val}'")

# Sort
sort_col = st.sidebar.selectbox("Sort by", options=["(none)", *col_names])
sort_dir = st.sidebar.radio("Sort direction", options=["ASC", "DESC"], horizontal=True)

# Build query
limit = st.sidebar.number_input("Row limit", min_value=10, max_value=10000, value=100, step=100)

where_sql = " AND ".join(where_clauses)
if where_sql:
    where_sql = f"WHERE {where_sql}"

order_sql = f'ORDER BY "{sort_col}" {sort_dir}' if sort_col != "(none)" else ""

query = f"SELECT * FROM {ref} {where_sql} {order_sql} LIMIT {limit}"

# Sample rows
st.subheader(f"Sample rows from `{selected_table}`")
try:
    df = conn.execute(query).fetchdf()
    st.dataframe(df, width="stretch", hide_index=True)
    st.caption(f"Showing {len(df)} rows")
except Exception as e:  # noqa: BLE001
    st.error(f"Query failed: {e}")

# Column stats
st.subheader("Column Statistics")

stats_col = st.selectbox("Column for stats", options=col_names)

if stats_col:

    @st.cache_data(show_spinner="Computing stats...")
    def compute_stats(dataset_name: str, table_name: str, col_name: str, file_path_str: str):
        c = get_connection()
        r = table_ref(Path(file_path_str))
        return c.execute(f"""
            SELECT
                count(*) as total_rows,
                count("{col_name}") as non_null,
                count(*) - count("{col_name}") as null_count,
                count(DISTINCT "{col_name}") as distinct_values
            FROM {r}
        """).fetchdf()

    try:
        stats = compute_stats(dataset.name, selected_table, stats_col, str(file_path))
        st.dataframe(stats, width="stretch", hide_index=True)
    except Exception as e:  # noqa: BLE001
        st.error(f"Stats computation failed: {e}")
        st.caption("This may happen with very large tables. Try a smaller table first.")
