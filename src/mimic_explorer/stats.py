"""Pre-compute and cache all static dataset statistics.

MIMIC datasets are static, so we compute stats once and save to disk as JSON.
Subsequent loads read from cache.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from mimic_explorer.config import HADM_TABLES
from mimic_explorer.db import (
    get_connection,
    resolve_note_ref,
    resolve_refs,
    scalar_query,
    table_ref,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from mimic_explorer.config import DatasetConfig

# Cache lives at the project root, outside src/. Gitignored so derived stats
# (which touch patient-level aggregates) never end up in version control.
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
        ],
    )
    is_mimic3 = cfg.uppercase_filenames

    # ICD join clause differs by version: MIMIC-III has only ICD-9 codes,
    # so a simple code match suffices. MIMIC-IV has both ICD-9 and ICD-10,
    # requiring icd_version in the join to avoid cross-version collisions.
    icd_col = cfg.col("icd_code")
    title_col = cfg.col("long_title")
    icd_join = f'd."{icd_col}" = t."{icd_col}"'
    if not is_mimic3:
        icd_join += ' AND d."icd_version" = t."icd_version"'

    note_ref = resolve_note_ref(cfg)

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
    _add_coverage_tasks(tasks, refs, note_ref, cfg=cfg)
    _add_data_quality_tasks(tasks, refs, note_ref, cfg=cfg)

    return tasks


# ---------------------------------------------------------------------------
# Task builders: volume, coverage, data quality
# ---------------------------------------------------------------------------


def _add_volume_tasks(
    tasks: dict[str, Any], refs: dict, note_ref: str | None, hadm_col: str
) -> None:
    """Per-admission volume: how many notes/labs/meds/procedures per stay."""
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


def _add_coverage_tasks(
    tasks: dict[str, Any],
    refs: dict,
    note_ref: str | None,
    *,
    cfg: DatasetConfig,
) -> None:
    """Table coverage: what percentage of admissions have at least one record.

    Low coverage means a table is only populated for certain stay types
    (e.g., ICU-only tables will show low coverage in MIMIC-IV, which
    includes non-ICU admissions).
    """
    if not refs["admissions"]:
        return
    adm_ref = refs["admissions"]
    hadm_col = cfg.col("hadm_id")

    # Build the list of tables to compute coverage for. Two filters:
    # 1. Must be on disk. The user may have downloaded a partial dataset
    #    (e.g. MIMIC-IV without the ICU module).
    # 2. Must have a hadm_id column. Coverage is "what fraction of
    #    admissions have at least one row in this table", which requires
    #    a join on hadm_id. HADM_TABLES is a static list from the schema
    #    reference, used to avoid opening each CSV.gz at runtime just to
    #    inspect its columns.
    # Skip admissions (don't count it against itself) and noteevents (only
    # present in MIMIC-III, and covered by the note_ref branch below so
    # both versions show the same "notes" label).
    tables = cfg.find_tables()
    coverage_tables: dict[str, str] = {}
    for name, path in tables.items():
        if name in ("admissions", "noteevents"):
            continue
        if name not in HADM_TABLES:
            continue
        coverage_tables[name] = table_ref(path)

    # MIMIC-III has a single NOTEEVENTS table. MIMIC-IV splits notes into
    # discharge + radiology in the MIMIC-IV-Note module, UNIONed by
    # resolve_note_ref. Both versions report under one "notes" label.
    if note_ref:
        coverage_tables["notes"] = note_ref

    for tname, tref in coverage_tables.items():
        tasks[f"coverage_{tname}"] = lambda tn=tname, tr=tref: _query_coverage(
            adm_ref, tr, hadm_col, tn
        )


def _add_data_quality_tasks(
    tasks: dict[str, Any],
    refs: dict,
    note_ref: str | None,
    *,
    cfg: DatasetConfig,
) -> None:
    """Data quality checks: missing timestamps and empty note text.

    These surface known data issues. MIMIC-III NOTEEVENTS has notes with
    NULL charttime (date-only entries) and empty text fields. MIMIC-IV-Note
    cleaned up some of these but still has missing charttimes.
    """
    if note_ref:
        tasks["dq_notes_missing_time"] = lambda: _query_dq_null_count(
            note_ref, cfg.col("charttime"), "Notes with missing timestamps"
        )
        tasks["dq_notes_empty"] = lambda: _query_dq_empty_text(
            note_ref, cfg.col("text"), "Empty notes"
        )
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

    coverage = {}
    for key, val in results.items():
        if key.startswith("coverage_") and val is not None:
            tname, pct = val
            coverage[tname] = pct
    if coverage:
        out["table_coverage"] = coverage

    dq_checks = [
        results[key]
        for key in ("dq_notes_missing_time", "dq_notes_empty", "dq_labs_missing_time")
        if key in results and results[key] is not None
    ]
    if dq_checks:
        out["data_quality"] = dq_checks

    return out


# ---------------------------------------------------------------------------
# Individual query functions. Each gets its own connection.
# ---------------------------------------------------------------------------


def _query_overview(cfg: DatasetConfig, tables: dict[str, Path]) -> dict:
    """Core dataset metrics for the "at a glance" page.

    Computes patient/admission/ICU counts, gender split, date range,
    mortality rate, and median length of stay. Uses a single connection
    for all queries since this runs in its own thread.
    """
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
    mortality_pct = scalar_query(
        conn,
        # hospital_expire_flag is 0 or 1, so avg() gives the fraction directly
        f'SELECT round(100.0 * avg("{death_col}"), 1) FROM {a}',
    )
    median_los = scalar_query(
        conn,
        f"""SELECT round(median(
            -- hours / 24 instead of date_diff('day'), which truncates
            -- (a 36-hour stay would show as 1 day instead of 1.5)
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
    """What are the most common diagnoses or procedures?

    Joins the fact table (diagnoses_icd, procedures_icd) against its dictionary
    table to resolve opaque ICD codes into human-readable descriptions.
    """
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
    """Which lab tests are ordered most frequently?

    Joins labevents against d_labitems to get test names from item IDs.
    """
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
    """What is the gender breakdown of the patient population?"""
    conn = get_connection()
    df = conn.execute(f"""
        SELECT "{gender_col}" AS gender, count(*) AS count
        FROM {pat_ref}
        GROUP BY "{gender_col}"
        ORDER BY count DESC
    """).fetchdf()
    return df.to_dict("records")


def _query_race_dist(adm_ref: str, race_col: str) -> list[dict]:
    """What is the race/ethnicity distribution across admissions?"""
    conn = get_connection()
    # MIMIC has 40+ race/ethnicity categories (many with small counts).
    # Top 15 covers the meaningful groups; the rest are shown as a pie chart
    # where too many tiny slices would be unreadable.
    df = conn.execute(f"""
        SELECT "{race_col}" AS race, count(*) AS count
        FROM {adm_ref}
        GROUP BY "{race_col}"
        ORDER BY count DESC
        LIMIT 15
    """).fetchdf()
    return df.to_dict("records")


def _query_age_dist(pat_ref: str, adm_ref: str, *, is_mimic3: bool) -> list[dict]:
    """Age distribution differs fundamentally between versions.

    MIMIC-III: age is computed per admission from DOB and ADMITTIME. Ages
    above 89 are capped at 90 for HIPAA de-identification. A patient
    admitted at 65 and again at 68 appears in both bins.

    MIMIC-IV: anchor_age is assigned once per patient at a reference year.
    Actual age at a specific admission may differ from anchor_age.
    """
    conn = get_connection()
    if is_mimic3:
        df = conn.execute(f"""
            SELECT
                -- Cap at 90: patients >89 have DOB shifted for HIPAA de-identification
                LEAST(
                    date_diff('year', "DOB"::TIMESTAMP, "ADMITTIME"::TIMESTAMP),
                    90
                ) AS age
            FROM {pat_ref} p
            JOIN {adm_ref} a ON p."SUBJECT_ID" = a."SUBJECT_ID"
        """).fetchdf()
    else:
        df = conn.execute(f"""
            -- anchor_age is assigned once per patient, not per admission
            SELECT "anchor_age" AS age
            FROM {pat_ref}
        """).fetchdf()
    return df.to_dict("records")


def _query_los_dist(adm_ref: str, admit_col: str, disch_col: str) -> list[dict]:
    """How long are patients hospitalized?"""
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
    """How much data is generated per hospital admission?

    Reports median, IQR, and max record counts per admission. A typical
    MIMIC-III admission has ~15 notes but hundreds of lab results.
    """
    conn = get_connection()
    row = conn.execute(f"""
        SELECT
            median(cnt)::INT AS median,
            quantile_cont(cnt, 0.25)::INT AS p25,
            quantile_cont(cnt, 0.75)::INT AS p75,
            max(cnt)::INT AS max
        FROM (
            -- Per-admission record counts
            SELECT "{hadm_col}", count(*) AS cnt
            FROM {tbl_ref}
            WHERE "{hadm_col}" IS NOT NULL
            GROUP BY "{hadm_col}"
        )
    """).fetchone()
    if not row:
        return (label, {})
    return (label, {"median": row[0], "p25": row[1], "p75": row[2], "max": row[3]})


def _query_coverage(
    adm_ref: str, tbl_ref: str, hadm_col: str, table_name: str
) -> tuple[str, float]:
    """What fraction of admissions have at least one record in this table?

    Uses a LEFT JOIN from admissions to count distinct hadm_ids that appear
    in the target table.
    """
    conn = get_connection()
    pct = scalar_query(
        conn,
        f"""
        SELECT round(100.0 * count(DISTINCT t."{hadm_col}") /
               -- NULLIF: guard against division by zero if admissions is empty
               NULLIF(count(DISTINCT a."{hadm_col}"), 0), 1)
        FROM {adm_ref} a
        LEFT JOIN {tbl_ref} t ON a."{hadm_col}" = t."{hadm_col}"
    """,
    )
    return (table_name, float(pct) if pct is not None else 0.0)


def _query_dq_null_count(tbl_ref: str, col: str, check_name: str) -> dict:
    """How many records are missing a value in the given column?"""
    conn = get_connection()
    total = scalar_query(conn, f"SELECT count(*) FROM {tbl_ref}")
    null_count = scalar_query(conn, f'SELECT count(*) FROM {tbl_ref} WHERE "{col}" IS NULL')
    pct = round(100.0 * null_count / total, 2) if total else 0.0
    return {"check": check_name, "count": null_count, "pct": pct}


def _query_dq_empty_text(tbl_ref: str, text_col: str, check_name: str) -> dict:
    """How many notes have NULL or whitespace-only text?"""
    conn = get_connection()
    total = scalar_query(conn, f"SELECT count(*) FROM {tbl_ref}")
    empty_count = scalar_query(
        conn,
        f'SELECT count(*) FROM {tbl_ref} WHERE "{text_col}" IS NULL OR TRIM("{text_col}") = \'\'',
    )
    pct = round(100.0 * empty_count / total, 2) if total else 0.0
    return {"check": check_name, "count": empty_count, "pct": pct}
