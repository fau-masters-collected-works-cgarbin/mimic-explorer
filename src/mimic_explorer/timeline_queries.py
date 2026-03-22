"""Data-fetching queries for the Clinical Timeline page.

Each function takes explicit parameters (connection, table refs, column names)
so they can be tested independently of Streamlit state.
"""

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from mimic_explorer.db import get_connection


def fetch_category_counts(
    noteevents_ref: str, category_col: str, error_filter: str | None
) -> pd.DataFrame:
    """Count notes by category across the entire dataset."""
    conn = get_connection()
    where = f"WHERE {error_filter}" if error_filter else ""
    return conn.execute(f"""
        SELECT "{category_col}" AS category, COUNT(*) AS count
        FROM {noteevents_ref}
        {where}
        GROUP BY "{category_col}"
        ORDER BY count DESC
    """).fetchdf()


def fetch_random_hadm_ids(
    noteevents_ref: str, hadm_col: str, error_filter: str | None
) -> list[int]:
    """Return up to 50 admission IDs that have 3+ notes.

    The 3-note minimum filters out admissions that are too sparse to produce
    a meaningful timeline. Sampling is done in DuckDB to avoid transferring
    the full list of qualifying admissions.
    """
    conn = get_connection()
    # Some notes have NULL hadm_id (e.g. outpatient notes not linked to an admission)
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


def fetch_admission_bounds(
    admissions_ref: str, hadm: int, hadm_col: str, admit_col: str, disch_col: str
) -> dict | None:
    """Return admit/discharge timestamps for a single admission, or None."""
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


def _fetch_notes(
    hadm: int,
    noteevents_ref: str,
    row_id_col: str,
    category_col: str,
    description_col: str,
    charttime_col: str,
    chartdate_col: str | None,
    hadm_col: str,
    error_filter: str | None,
) -> pd.DataFrame:
    """Fetch notes for an admission, ordered by charttime with chartdate fallback.

    MIMIC-III notes may have charttime or only chartdate (date without time).
    When both exist, COALESCE prefers the more precise charttime. MIMIC-IV
    notes always have charttime, so chartdate_col is None and no fallback is needed.
    """
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


def _fetch_abnormal_labs(hadm: int, ref: str | None, lab_cols: dict) -> pd.DataFrame:
    if ref is None:
        return pd.DataFrame()
    c = lab_cols  # short alias for use in the SQL template
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
          -- Flag is empty string (not NULL) for normal results in MIMIC-III
          AND "{c["flag"]}" IS NOT NULL AND "{c["flag"]}" != ''
          AND "{c["charttime"]}" IS NOT NULL
        ORDER BY "{c["charttime"]}"
    """,
        [hadm],
    ).fetchdf()


def _fetch_transfers(hadm: int, ref: str | None, xfer_cols: dict) -> pd.DataFrame:
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


def _fetch_meds(hadm: int, ref: str | None, rx_cols: dict) -> pd.DataFrame:
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


def fetch_admission_data(
    hadm: int,
    noteevents_ref: str,
    lab_ref: str | None,
    xfer_ref: str | None,
    rx_ref: str | None,
    *,
    note_cols: dict,
    lab_cols: dict,
    xfer_cols: dict,
    rx_cols: dict,
) -> dict[str, pd.DataFrame]:
    """Fetch notes and structured events for a single admission.

    Returns a dict with keys "notes", "labs", "transfers", "meds", each a DataFrame.
    Queries run in parallel. Each thread creates its own DuckDB connection because
    DuckDB connections are not thread-safe.
    """
    with ThreadPoolExecutor(max_workers=4) as pool:
        notes_future = pool.submit(_fetch_notes, hadm, noteevents_ref, **note_cols)
        lab_future = pool.submit(_fetch_abnormal_labs, hadm, lab_ref, lab_cols)
        xfer_future = pool.submit(_fetch_transfers, hadm, xfer_ref, xfer_cols)
        med_future = pool.submit(_fetch_meds, hadm, rx_ref, rx_cols)
    return {
        "notes": notes_future.result(),
        "labs": lab_future.result(),
        "transfers": xfer_future.result(),
        "meds": med_future.result(),
    }


def fetch_note_text(noteevents_ref: str, rid: str, text_col: str, row_id_col: str) -> str | None:
    """Fetch the full text of a single note by its row/note ID.

    The CAST to VARCHAR handles the type mismatch between MIMIC-III (ROW_ID is
    integer) and MIMIC-IV (note_id is string), so the same query works for both.
    """
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
