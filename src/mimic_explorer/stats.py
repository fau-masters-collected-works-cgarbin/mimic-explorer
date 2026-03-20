"""Pre-compute and cache all static dataset statistics.

MIMIC datasets are static, so we compute stats once and save to disk as JSON.
Subsequent loads read from cache for instant startup.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from mimic_explorer.db import get_connection, note_union_ref, resolve_refs, scalar_query, table_ref

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from mimic_explorer.config import DatasetConfig

CACHE_DIR = Path(__file__).resolve().parents[2] / ".mimic_explorer_cache"


def load_stats(dataset_key: str) -> dict | None:
    """Read cached stats from disk. Returns None if not cached."""
    path = CACHE_DIR / f"{dataset_key}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


class _NumpyEncoder(json.JSONEncoder):
    """Encode numpy types to native Python types for JSON serialization.

    pandas DataFrames return numpy types from to_dict("records"). These aren't
    JSON-serializable by default, so we convert them here.
    """

    def default(self, o: object) -> object:
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)


def save_stats(dataset_key: str, data: dict) -> None:
    """Write stats to disk as JSON."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{dataset_key}.json"
    path.write_text(json.dumps(data, cls=_NumpyEncoder))


def compute_stats(cfg: DatasetConfig) -> dict:
    """Run all stats queries in parallel and return the combined dict."""
    tasks = _build_tasks(cfg)

    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            task_name = futures[future]
            try:
                results[task_name] = future.result()
            except Exception:
                logger.exception("Stats query '%s' failed", task_name)

    return _assemble_stats(results)


def _build_tasks(cfg: DatasetConfig) -> dict[str, Any]:
    """Build the dict of named tasks (callables) for parallel execution."""
    tables = cfg.find_tables()
    note_tables = cfg.find_note_tables()
    refs = resolve_refs(
        tables,
        [
            "patients",
            "admissions",
            "icustays",
            "diagnoses_icd",
            "procedures_icd",
            "d_icd_diagnoses",
            "d_icd_procedures",
            "d_labitems",
            "labevents",
            "prescriptions",
            "transfers",
            "noteevents",
        ],
    )
    is_mimic3 = cfg.uppercase_filenames

    icd_col = cfg.col("icd_code")
    title_col = cfg.col("long_title")
    icd_join = f'd."{icd_col}" = t."{icd_col}"'
    if not is_mimic3:
        icd_join += ' AND d."icd_version" = t."icd_version"'

    note_ref = refs["noteevents"]
    if not is_mimic3 and note_tables:
        note_ref = note_union_ref(note_tables)

    tasks: dict[str, Any] = {}
    tasks["overview"] = lambda: _query_overview(cfg, tables)

    if refs["diagnoses_icd"] and refs["d_icd_diagnoses"]:
        tasks["top_diagnoses"] = lambda: _query_top_coded(
            refs["diagnoses_icd"], refs["d_icd_diagnoses"], icd_join, title_col, "diagnosis"
        )
    if refs["procedures_icd"] and refs["d_icd_procedures"]:
        tasks["top_procedures"] = lambda: _query_top_coded(
            refs["procedures_icd"], refs["d_icd_procedures"], icd_join, title_col, "procedure"
        )
    if refs["labevents"] and refs["d_labitems"]:
        tasks["top_labs"] = lambda: _query_top_labs(
            refs["labevents"], refs["d_labitems"], cfg.col("itemid"), cfg.col("label")
        )
    if refs["patients"]:
        tasks["gender_dist"] = lambda: _query_gender_dist(refs["patients"], cfg.col("gender"))
    if refs["admissions"]:
        tasks["race_dist"] = lambda: _query_race_dist(refs["admissions"], cfg.col("race"))
    if refs["patients"] and refs["admissions"]:
        tasks["age_dist"] = lambda: _query_age_dist(
            refs["patients"], refs["admissions"], is_mimic3=is_mimic3
        )
    if refs["admissions"]:
        tasks["los_dist"] = lambda: _query_los_dist(
            refs["admissions"], cfg.col("admittime"), cfg.col("dischtime")
        )

    hadm_col = cfg.col("hadm_id")
    _add_volume_tasks(tasks, refs, note_ref, hadm_col)
    _add_sparsity_tasks(tasks, refs, note_ref, is_mimic3=is_mimic3, hadm_col=hadm_col)
    _add_data_quality_tasks(tasks, refs, note_ref, is_mimic3=is_mimic3, cfg=cfg)

    return tasks


def _add_volume_tasks(
    tasks: dict[str, Any], refs: dict, note_ref: str | None, hadm_col: str
) -> None:
    if note_ref:
        tasks["vol_notes"] = lambda: _query_per_admission_volume(note_ref, hadm_col, "Notes")
    if refs["labevents"]:
        tasks["vol_labs"] = lambda: _query_per_admission_volume(refs["labevents"], hadm_col, "Labs")
    if refs["prescriptions"]:
        tasks["vol_meds"] = lambda: _query_per_admission_volume(
            refs["prescriptions"], hadm_col, "Medications"
        )
    if refs["procedures_icd"]:
        tasks["vol_procs"] = lambda: _query_per_admission_volume(
            refs["procedures_icd"], hadm_col, "Procedures"
        )


def _add_sparsity_tasks(
    tasks: dict[str, Any],
    refs: dict,
    note_ref: str | None,
    *,
    is_mimic3: bool,
    hadm_col: str,
) -> None:
    if not refs["admissions"]:
        return
    sparsity_tables = {
        "diagnoses_icd": refs["diagnoses_icd"],
        "procedures_icd": refs["procedures_icd"],
        "labevents": refs["labevents"],
        "prescriptions": refs["prescriptions"],
        "transfers": refs["transfers"],
    }
    if is_mimic3:
        sparsity_tables["noteevents"] = refs["noteevents"]
    elif note_ref:
        sparsity_tables["notes"] = note_ref

    for tname, tref in sparsity_tables.items():
        if tref:
            tasks[f"sparsity_{tname}"] = lambda tn=tname, tr=tref: _query_sparsity(
                refs["admissions"], tr, hadm_col, tn
            )


def _add_data_quality_tasks(
    tasks: dict[str, Any],
    refs: dict,
    note_ref: str | None,
    *,
    is_mimic3: bool,
    cfg: DatasetConfig,
) -> None:
    if is_mimic3 and refs["noteevents"]:
        tasks["dq_notes_missing_time"] = lambda: _query_dq_null_count(
            refs["noteevents"],
            cfg.col("charttime"),
            "Notes with missing timestamps",
        )
        tasks["dq_notes_empty"] = lambda: _query_dq_empty_text(
            refs["noteevents"], cfg.col("text"), "Empty notes"
        )
    elif note_ref and not is_mimic3:
        tasks["dq_notes_missing_time"] = lambda: _query_dq_null_count(
            note_ref, "charttime", "Notes with missing timestamps"
        )
        tasks["dq_notes_empty"] = lambda: _query_dq_empty_text(note_ref, "text", "Empty notes")
    if refs["labevents"]:
        tasks["dq_labs_missing_time"] = lambda: _query_dq_null_count(
            refs["labevents"], cfg.col("charttime"), "Labs with missing timestamps"
        )


def _assemble_stats(results: dict[str, Any]) -> dict[str, Any]:
    """Combine parallel query results into the final stats dict."""
    out: dict[str, Any] = {}
    out["overview"] = results.get("overview", {})

    for key in (
        "top_diagnoses",
        "top_procedures",
        "top_labs",
        "gender_dist",
        "race_dist",
        "age_dist",
        "los_dist",
    ):
        if key in results:
            out[key] = results[key]

    volume = {}
    for vkey in ("vol_notes", "vol_labs", "vol_meds", "vol_procs"):
        if val := results.get(vkey):
            label, stats = val
            volume[label] = stats
    if volume:
        out["per_admission_volume"] = volume

    sparsity = {}
    for key, val in results.items():
        if key.startswith("sparsity_") and val is not None:
            tname, pct = val
            sparsity[tname] = pct
    if sparsity:
        out["table_sparsity"] = sparsity

    dq_checks = [
        results[key]
        for key in ("dq_notes_missing_time", "dq_notes_empty", "dq_labs_missing_time")
        if key in results and results[key] is not None
    ]
    if dq_checks:
        out["data_quality"] = dq_checks

    return out


# ---------------------------------------------------------------------------
# Individual query functions -- each gets its own connection
# ---------------------------------------------------------------------------


def _query_overview(cfg: DatasetConfig, tables: dict[str, Path]) -> dict:
    conn = get_connection()
    patients_path = tables.get("patients")
    admissions_path = tables.get("admissions")
    icustays_path = tables.get("icustays")

    if not patients_path or not admissions_path:
        return {}

    p = table_ref(patients_path)
    a = table_ref(admissions_path)
    gender_col = cfg.col("gender")
    admit_col = cfg.col("admittime")
    disch_col = cfg.col("dischtime")
    death_col = cfg.col("hospital_expire_flag")
    los_col = cfg.col("los")

    total_patients = scalar_query(conn, f"SELECT count(*) FROM {p}")
    total_admissions = scalar_query(conn, f"SELECT count(*) FROM {a}")
    male_pct = scalar_query(
        conn,
        f"SELECT round(100.0 * count(*) FILTER "
        f"(WHERE \"{gender_col}\" = 'M') / count(*), 1) FROM {p}",
    )
    min_admit = scalar_query(conn, f'SELECT min("{admit_col}")::DATE FROM {a}')
    max_admit = scalar_query(conn, f'SELECT max("{admit_col}")::DATE FROM {a}')
    mortality_pct = scalar_query(conn, f'SELECT round(100.0 * avg("{death_col}"), 1) FROM {a}')
    median_los = scalar_query(
        conn,
        f"""SELECT round(median(
            date_diff('hour', "{admit_col}"::TIMESTAMP, "{disch_col}"::TIMESTAMP) / 24.0
        ), 1) FROM {a}""",
    )

    total_icu_stays = None
    median_icu_los = None
    if icustays_path:
        i = table_ref(icustays_path)
        total_icu_stays = scalar_query(conn, f"SELECT count(*) FROM {i}")
        median_icu_los = scalar_query(conn, f'SELECT round(median("{los_col}"), 1) FROM {i}')

    return {
        "total_patients": total_patients,
        "total_admissions": total_admissions,
        "male_pct": male_pct,
        "min_admit": str(min_admit),
        "max_admit": str(max_admit),
        "mortality_pct": mortality_pct,
        "median_los": median_los,
        "total_icu_stays": total_icu_stays,
        "median_icu_los": median_icu_los,
    }


def _query_top_coded(
    fact_ref: str, dict_ref: str, join_clause: str, title_col: str, label: str
) -> list[dict]:
    conn = get_connection()
    df = conn.execute(f"""
        SELECT d."{title_col}" AS {label}, count(*) AS count
        FROM {fact_ref} t
        JOIN {dict_ref} d ON {join_clause}
        GROUP BY d."{title_col}"
        ORDER BY count DESC
        LIMIT 20
    """).fetchdf()
    return df.to_dict("records")


def _query_top_labs(lab_ref: str, dlab_ref: str, item_col: str, lbl_col: str) -> list[dict]:
    conn = get_connection()
    # No sampling: scan the full table for exact counts
    df = conn.execute(f"""
        SELECT d."{lbl_col}" AS lab_test, count(*) AS count
        FROM {lab_ref} t
        JOIN {dlab_ref} d ON d."{item_col}" = t."{item_col}"
        GROUP BY d."{lbl_col}"
        ORDER BY count DESC
        LIMIT 20
    """).fetchdf()
    return df.to_dict("records")


def _query_gender_dist(pat_ref: str, gender_col: str) -> list[dict]:
    conn = get_connection()
    df = conn.execute(f"""
        SELECT "{gender_col}" AS gender, count(*) AS count
        FROM {pat_ref}
        GROUP BY "{gender_col}"
        ORDER BY count DESC
    """).fetchdf()
    return df.to_dict("records")


def _query_race_dist(adm_ref: str, race_col: str) -> list[dict]:
    conn = get_connection()
    df = conn.execute(f"""
        SELECT "{race_col}" AS race, count(*) AS count
        FROM {adm_ref}
        GROUP BY "{race_col}"
        ORDER BY count DESC
        LIMIT 15
    """).fetchdf()
    return df.to_dict("records")


def _query_age_dist(pat_ref: str, adm_ref: str, *, is_mimic3: bool) -> list[dict]:
    conn = get_connection()
    if is_mimic3:
        df = conn.execute(f"""
            SELECT
                LEAST(
                    date_diff('year', "DOB"::TIMESTAMP, "ADMITTIME"::TIMESTAMP),
                    90
                ) AS age
            FROM {pat_ref} p
            JOIN {adm_ref} a ON p."SUBJECT_ID" = a."SUBJECT_ID"
        """).fetchdf()
    else:
        df = conn.execute(f"""
            SELECT "anchor_age" AS age
            FROM {pat_ref}
        """).fetchdf()
    return df.to_dict("records")


def _query_los_dist(adm_ref: str, admit_col: str, disch_col: str) -> list[dict]:
    conn = get_connection()
    df = conn.execute(f"""
        SELECT
            date_diff('hour',
                "{admit_col}"::TIMESTAMP,
                "{disch_col}"::TIMESTAMP
            ) / 24.0 AS los_days
        FROM {adm_ref}
        WHERE "{disch_col}" IS NOT NULL
    """).fetchdf()
    return df.to_dict("records")


def _query_per_admission_volume(tbl_ref: str, hadm_col: str, label: str) -> tuple[str, dict]:
    conn = get_connection()
    row = conn.execute(f"""
        SELECT
            median(cnt)::INT AS median,
            quantile_cont(cnt, 0.25)::INT AS p25,
            quantile_cont(cnt, 0.75)::INT AS p75,
            max(cnt)::INT AS max
        FROM (
            SELECT "{hadm_col}", count(*) AS cnt
            FROM {tbl_ref}
            WHERE "{hadm_col}" IS NOT NULL
            GROUP BY "{hadm_col}"
        )
    """).fetchone()
    if not row:
        return (label, {})
    return (label, {"median": row[0], "p25": row[1], "p75": row[2], "max": row[3]})


def _query_sparsity(
    adm_ref: str, tbl_ref: str, hadm_col: str, table_name: str
) -> tuple[str, float]:
    conn = get_connection()
    pct = scalar_query(
        conn,
        f"""
        SELECT round(100.0 * count(DISTINCT t."{hadm_col}") /
               NULLIF(count(DISTINCT a."{hadm_col}"), 0), 1)
        FROM {adm_ref} a
        LEFT JOIN {tbl_ref} t ON a."{hadm_col}" = t."{hadm_col}"
    """,
    )
    return (table_name, float(pct) if pct is not None else 0.0)


def _query_dq_null_count(tbl_ref: str, col: str, check_name: str) -> dict:
    conn = get_connection()
    total = scalar_query(conn, f"SELECT count(*) FROM {tbl_ref}")
    null_count = scalar_query(conn, f'SELECT count(*) FROM {tbl_ref} WHERE "{col}" IS NULL')
    pct = round(100.0 * null_count / total, 2) if total else 0.0
    return {"check": check_name, "count": null_count, "pct": pct}


def _query_dq_empty_text(tbl_ref: str, text_col: str, check_name: str) -> dict:
    conn = get_connection()
    total = scalar_query(conn, f"SELECT count(*) FROM {tbl_ref}")
    empty_count = scalar_query(
        conn,
        f'SELECT count(*) FROM {tbl_ref} WHERE "{text_col}" IS NULL OR TRIM("{text_col}") = \'\'',
    )
    pct = round(100.0 * empty_count / total, 2) if total else 0.0
    return {"check": check_name, "count": empty_count, "pct": pct}
