"""Table Browser -- sample rows, column stats, filter and sort."""

from pathlib import Path

import streamlit as st

from mimic_explorer.config import DATASETS, LARGE_TABLES
from mimic_explorer.db import column_info, get_connection, table_ref

st.title("Table Browser")

dataset = DATASETS[st.session_state["dataset_key"]]
st.caption(f"Showing: {dataset.name}")
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
    return column_info(c, Path(file_path_str))


columns = get_columns(dataset.name, selected_table, str(file_path))
col_names = [c["name"] for c in columns]

# Filters
NUMERIC_TYPES = {"BIGINT", "INTEGER", "DOUBLE", "FLOAT", "DECIMAL"}

st.sidebar.subheader("Filters")
where_clauses = []
for col in columns[:10]:  # Show filter inputs for the first 10 columns only
    val = st.sidebar.text_input(f"{col['name']} =", key=f"filter_{col['name']}")
    if val:
        if col["type"] in NUMERIC_TYPES:
            try:
                numeric_val = float(val)
            except ValueError:
                st.sidebar.error(f"'{val}' is not a valid number for {col['name']}")
                continue
            where_clauses.append(f'"{col["name"]}" = {numeric_val}')
        else:
            # Escape single quotes to prevent SQL injection
            escaped = val.replace("'", "''")
            where_clauses.append(f"\"{col['name']}\" = '{escaped}'")

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
