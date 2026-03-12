# Agent Guidelines

## Project overview

Streamlit database explorer for MIMIC-III and MIMIC-IV clinical datasets. Uses DuckDB to query CSV.gz files directly (no ETL, no database). Phase 0a of the dissertation execution plan: understand the data before building experiments.

## Architecture

- `app.py` -- Streamlit entry point, dataset selector sidebar, `st.navigation()` page routing. UI only.
- `src/mimic_explorer/config.py` -- Dataset path configuration, table discovery. No UI imports.
- `src/mimic_explorer/db.py` -- DuckDB connection, `table_ref()` resolver, query helpers. No UI imports.
- `pages/dataset_at_a_glance.py` -- Key dataset metrics and contextual explanations for newcomers. UI only, uses db and config.
- `pages/database_schema.py` -- Join key hierarchy, tables grouped by connectivity with column details in expanders, join patterns. UI only, uses db and config.
- `pages/clinical_insights.py` -- Distributions: top diagnoses/procedures/labs, demographics, LOS. UI only, uses db.
- `pages/note_timeline.py` -- Temporal note distribution across hospital stays. Category overview, per-admission timeline, temporal density, note-to-note intervals, note text viewer. UI only, uses db and config. MIMIC-III only (NOTEEVENTS); MIMIC-IV-Note support structured but not yet active.
- `pages/community_references.py` -- Links to external MIMIC resources. Static content, no data queries.

## Git workflow

- Work in worktrees (`isolation: "worktree"`), not the main working directory.
- Always rebase, never merge. Keep history linear.
- Push directly to `main` when done — no PRs for single-author work.

## Setup

```bash
uv sync --all-groups
pre-commit install
```

## Running the app

```bash
uv run streamlit run app.py
```

## Running tests

```bash
uv run pytest tests/ -v
```

Run tests after every change to `config.py` or `db.py`.

## Linting and formatting

```bash
uv run ruff check .
uv run ruff format .
```

Pre-commit hooks run ruff automatically on commit.

## Code style

- Python 3.11+ features are fine.
- Type hints on function signatures in logic modules (`config.py`, `db.py`).
- Annotations optional in Streamlit pages and `app.py`.
- S608 (SQL injection) suppressed for DuckDB file reads -- all SQL is built from local file paths, not user input.
- Page ordering is controlled via `st.navigation()` in `app.py`, not filename prefixes. Pages must not call `st.set_page_config()`.

## Testing philosophy

- Test `config.py` and `db.py` with synthetic CSV.gz fixtures (see `tests/conftest.py`).
- Don't test Streamlit pages -- business logic lives in the logic modules.
- Mock nothing for now -- DuckDB reads temp files directly in tests.

## Key design decisions

- DuckDB reads CSV.gz directly via `read_csv_auto()`. No ETL step.
- `table_ref(path)` returns a SQL fragment: `read_csv_auto('/path/to/file.csv.gz')`.
- Large tables (CHARTEVENTS, LABEVENTS) are skipped by default in row counts.
- MIMIC-III uses flat directory with UPPERCASE filenames; MIMIC-IV uses hosp/icu subdirs with lowercase.

## Streamlit caching

- `st.cache_data` parameters prefixed with `_` are excluded from the cache key.
- Always include the dataset name as a non-prefixed parameter so the cache invalidates when the user switches datasets.
- ARG001 is suppressed for pages because cache-key-only parameters are intentional.
- Use `width="stretch"` instead of `use_container_width=True` for `st.plotly_chart` and `st.dataframe`.

## MIMIC schema reference

Verified against local CSV.gz files. Use this instead of looking up columns at runtime when writing version-aware code.

### Version differences

| Concept | MIMIC-III | MIMIC-IV |
|---|---|---|
| Column case | UPPERCASE | lowercase |
| Directory layout | flat | hosp/, icu/ subdirs |
| ICU stay key | ICUSTAY_ID | stay_id |
| ICD code column | ICD9_CODE | icd_code + icd_version |
| Diagnosis title join | d.ICD9_CODE = t.ICD9_CODE | d.icd_code = t.icd_code AND d.icd_version = t.icd_version |
| Patient age | Compute from DOB and ADMITTIME (cap at 90 for >89 de-identification) | anchor_age (directly available) |
| Race/ethnicity column | ETHNICITY (in ADMISSIONS) | race (in admissions) |
| Input events | INPUTEVENTS_CV (CareVue) + INPUTEVENTS_MV (MetaVision) | inputevents (unified) |
| Procedure events | PROCEDUREEVENTS_MV (MetaVision only) | procedureevents |
| Clinical notes | NOTEEVENTS | Not in base MIMIC-IV; separate mimic-iv-note module |
| ROW_ID column | Present in all tables | Removed |

### Join key hierarchy

`subject_id` (patient) → `hadm_id` (hospital admission) → `icustay_id`/`stay_id` (ICU stay)

### MIMIC-IV tables and columns

**hosp/patients**: subject_id, gender, anchor_age, anchor_year, anchor_year_group, dod

**hosp/admissions**: subject_id, hadm_id, admittime, dischtime, deathtime, admission_type, admit_provider_id, admission_location, discharge_location, insurance, language, marital_status, race, edregtime, edouttime, hospital_expire_flag

**icu/icustays**: subject_id, hadm_id, stay_id, first_careunit, last_careunit, intime, outtime, los

**hosp/diagnoses_icd**: subject_id, hadm_id, seq_num, icd_code, icd_version

**hosp/procedures_icd**: subject_id, hadm_id, seq_num, chartdate, icd_code, icd_version

**hosp/labevents**: labevent_id, subject_id, hadm_id, specimen_id, itemid, order_provider_id, charttime, storetime, value, valuenum, valueuom, ref_range_lower, ref_range_upper, flag, priority, comments

**hosp/prescriptions**: subject_id, hadm_id, pharmacy_id, poe_id, poe_seq, order_provider_id, starttime, stoptime, drug_type, drug, formulary_drug_cd, gsn, ndc, prod_strength, form_rx, dose_val_rx, dose_unit_rx, form_val_disp, form_unit_disp, doses_per_24_hrs, route

**hosp/microbiologyevents**: microevent_id, subject_id, hadm_id, micro_specimen_id, order_provider_id, chartdate, charttime, spec_itemid, spec_type_desc, test_seq, storedate, storetime, test_itemid, test_name, org_itemid, org_name, isolate_num, quantity, ab_itemid, ab_name, dilution_text, dilution_comparison, dilution_value, interpretation, comments

**hosp/transfers**: subject_id, hadm_id, transfer_id, eventtype, careunit, intime, outtime

**hosp/services**: subject_id, hadm_id, transfertime, prev_service, curr_service

**hosp/drgcodes**: subject_id, hadm_id, drg_type, drg_code, description, drg_severity, drg_mortality

**hosp/emar**: subject_id, hadm_id, emar_id, emar_seq, poe_id, pharmacy_id, enter_provider_id, charttime, medication, event_txt, scheduletime, storetime

**hosp/emar_detail**: subject_id, emar_id, emar_seq, parent_field_ordinal, administration_type, pharmacy_id, barcode_type, reason_for_no_barcode, complete_dose_not_given, dose_due, dose_due_unit, dose_given, dose_given_unit, will_remainder_of_dose_be_given, product_amount_given, product_unit, product_code, product_description, product_description_other, prior_infusion_rate, infusion_rate, infusion_rate_adjustment, infusion_rate_adjustment_amount, infusion_rate_unit, route, infusion_complete, completion_interval, new_iv_bag_hung, continued_infusion_in_other_location, restart_interval, side, site, non_formulary_visual_verification

**hosp/pharmacy**: subject_id, hadm_id, pharmacy_id, poe_id, starttime, stoptime, medication, proc_type, status, entertime, verifiedtime, route, frequency, disp_sched, infusion_type, sliding_scale, lockout_interval, basal_rate, one_hr_max, doses_per_24_hrs, duration, duration_interval, expiration_value, expiration_unit, expirationdate, dispensation, fill_quantity

**hosp/poe**: poe_id, poe_seq, subject_id, hadm_id, ordertime, order_type, order_subtype, transaction_type, discontinue_of_poe_id, discontinued_by_poe_id, order_provider_id, order_status

**hosp/poe_detail**: poe_id, poe_seq, subject_id, field_name, field_value

**hosp/hcpcsevents**: subject_id, hadm_id, chartdate, hcpcs_cd, seq_num, short_description

**hosp/omr**: subject_id, chartdate, seq_num, result_name, result_value

**hosp/provider**: provider_id

**Dictionary tables (hosp)**:
- **d_icd_diagnoses**: icd_code, icd_version, long_title
- **d_icd_procedures**: icd_code, icd_version, long_title
- **d_labitems**: itemid, label, fluid, category
- **d_hcpcs**: code, category, long_description, short_description

**icu/chartevents**: subject_id, hadm_id, stay_id, caregiver_id, charttime, storetime, itemid, value, valuenum, valueuom, warning

**icu/inputevents**: subject_id, hadm_id, stay_id, caregiver_id, starttime, endtime, storetime, itemid, amount, amountuom, rate, rateuom, orderid, linkorderid, ordercategoryname, secondaryordercategoryname, ordercomponenttypedescription, ordercategorydescription, patientweight, totalamount, totalamountuom, isopenbag, continueinnextdept, statusdescription, originalamount, originalrate

**icu/outputevents**: subject_id, hadm_id, stay_id, caregiver_id, charttime, storetime, itemid, value, valueuom

**icu/procedureevents**: subject_id, hadm_id, stay_id, caregiver_id, starttime, endtime, storetime, itemid, value, valueuom, location, locationcategory, orderid, linkorderid, ordercategoryname, ordercategorydescription, patientweight, isopenbag, continueinnextdept, statusdescription, originalamount, originalrate

**icu/ingredientevents**: subject_id, hadm_id, stay_id, caregiver_id, starttime, endtime, storetime, itemid, amount, amountuom, rate, rateuom, orderid, linkorderid, statusdescription, originalamount, originalrate

**icu/datetimeevents**: subject_id, hadm_id, stay_id, caregiver_id, charttime, storetime, itemid, value, valueuom, warning

**Dictionary tables (icu)**:
- **d_items**: itemid, label, abbreviation, linksto, category, unitname, param_type, lownormalvalue, highnormalvalue

**icu/caregiver**: caregiver_id

### MIMIC-III tables and columns

**PATIENTS**: ROW_ID, SUBJECT_ID, GENDER, DOB, DOD, DOD_HOSP, DOD_SSN, EXPIRE_FLAG

**ADMISSIONS**: ROW_ID, SUBJECT_ID, HADM_ID, ADMITTIME, DISCHTIME, DEATHTIME, ADMISSION_TYPE, ADMISSION_LOCATION, DISCHARGE_LOCATION, INSURANCE, LANGUAGE, RELIGION, MARITAL_STATUS, ETHNICITY, EDREGTIME, EDOUTTIME, DIAGNOSIS, HOSPITAL_EXPIRE_FLAG, HAS_CHARTEVENTS_DATA

**ICUSTAYS**: ROW_ID, SUBJECT_ID, HADM_ID, ICUSTAY_ID, DBSOURCE, FIRST_CAREUNIT, LAST_CAREUNIT, FIRST_WARDID, LAST_WARDID, INTIME, OUTTIME, LOS

**DIAGNOSES_ICD**: ROW_ID, SUBJECT_ID, HADM_ID, SEQ_NUM, ICD9_CODE

**PROCEDURES_ICD**: ROW_ID, SUBJECT_ID, HADM_ID, SEQ_NUM, ICD9_CODE

**LABEVENTS**: ROW_ID, SUBJECT_ID, HADM_ID, ITEMID, CHARTTIME, VALUE, VALUENUM, VALUEUOM, FLAG

**PRESCRIPTIONS**: ROW_ID, SUBJECT_ID, HADM_ID, ICUSTAY_ID, STARTDATE, ENDDATE, DRUG_TYPE, DRUG, DRUG_NAME_POE, DRUG_NAME_GENERIC, FORMULARY_DRUG_CD, GSN, NDC, PROD_STRENGTH, DOSE_VAL_RX, DOSE_UNIT_RX, FORM_VAL_DISP, FORM_UNIT_DISP, ROUTE

**NOTEEVENTS**: ROW_ID, SUBJECT_ID, HADM_ID, CHARTDATE, CHARTTIME, STORETIME, CATEGORY, DESCRIPTION, CGID, ISERROR, TEXT

**MICROBIOLOGYEVENTS**: ROW_ID, SUBJECT_ID, HADM_ID, CHARTDATE, CHARTTIME, SPEC_ITEMID, SPEC_TYPE_DESC, ORG_ITEMID, ORG_NAME, ISOLATE_NUM, AB_ITEMID, AB_NAME, DILUTION_TEXT, DILUTION_COMPARISON, DILUTION_VALUE, INTERPRETATION

**CHARTEVENTS**: ROW_ID, SUBJECT_ID, HADM_ID, ICUSTAY_ID, ITEMID, CHARTTIME, STORETIME, CGID, VALUE, VALUENUM, VALUEUOM, WARNING, ERROR, RESULTSTATUS, STOPPED

**INPUTEVENTS_CV**: ROW_ID, SUBJECT_ID, HADM_ID, ICUSTAY_ID, CHARTTIME, ITEMID, AMOUNT, AMOUNTUOM, RATE, RATEUOM, STORETIME, CGID, ORDERID, LINKORDERID, STOPPED, NEWBOTTLE, ORIGINALAMOUNT, ORIGINALAMOUNTUOM, ORIGINALROUTE, ORIGINALRATE, ORIGINALRATEUOM, ORIGINALSITE

**INPUTEVENTS_MV**: ROW_ID, SUBJECT_ID, HADM_ID, ICUSTAY_ID, STARTTIME, ENDTIME, ITEMID, AMOUNT, AMOUNTUOM, RATE, RATEUOM, STORETIME, CGID, ORDERID, LINKORDERID, ORDERCATEGORYNAME, SECONDARYORDERCATEGORYNAME, ORDERCOMPONENTTYPEDESCRIPTION, ORDERCATEGORYDESCRIPTION, PATIENTWEIGHT, TOTALAMOUNT, TOTALAMOUNTUOM, ISOPENBAG, CONTINUEINNEXTDEPT, CANCELREASON, STATUSDESCRIPTION, COMMENTS_EDITEDBY, COMMENTS_CANCELEDBY, COMMENTS_DATE, ORIGINALAMOUNT, ORIGINALRATE

**OUTPUTEVENTS**: ROW_ID, SUBJECT_ID, HADM_ID, ICUSTAY_ID, CHARTTIME, ITEMID, VALUE, VALUEUOM, STORETIME, CGID, STOPPED, NEWBOTTLE, ISERROR

**PROCEDUREEVENTS_MV**: ROW_ID, SUBJECT_ID, HADM_ID, ICUSTAY_ID, STARTTIME, ENDTIME, ITEMID, VALUE, VALUEUOM, LOCATION, LOCATIONCATEGORY, STORETIME, CGID, ORDERID, LINKORDERID, ORDERCATEGORYNAME, SECONDARYORDERCATEGORYNAME, ORDERCATEGORYDESCRIPTION, ISOPENBAG, CONTINUEINNEXTDEPT, CANCELREASON, STATUSDESCRIPTION, COMMENTS_EDITEDBY, COMMENTS_CANCELEDBY, COMMENTS_DATE

**DATETIMEEVENTS**: ROW_ID, SUBJECT_ID, HADM_ID, ICUSTAY_ID, ITEMID, CHARTTIME, STORETIME, CGID, VALUE, VALUEUOM, WARNING, ERROR, RESULTSTATUS, STOPPED

**TRANSFERS**: ROW_ID, SUBJECT_ID, HADM_ID, ICUSTAY_ID, DBSOURCE, EVENTTYPE, PREV_CAREUNIT, CURR_CAREUNIT, PREV_WARDID, CURR_WARDID, INTIME, OUTTIME, LOS

**SERVICES**: ROW_ID, SUBJECT_ID, HADM_ID, TRANSFERTIME, PREV_SERVICE, CURR_SERVICE

**CALLOUT**: ROW_ID, SUBJECT_ID, HADM_ID, SUBMIT_WARDID, SUBMIT_CAREUNIT, CURR_WARDID, CURR_CAREUNIT, CALLOUT_WARDID, CALLOUT_SERVICE, REQUEST_TELE, REQUEST_RESP, REQUEST_CDIFF, REQUEST_MRSA, REQUEST_VRE, CALLOUT_STATUS, CALLOUT_OUTCOME, DISCHARGE_WARDID, ACKNOWLEDGE_STATUS, CREATETIME, UPDATETIME, ACKNOWLEDGETIME, OUTCOMETIME, FIRSTRESERVATIONTIME, CURRENTRESERVATIONTIME

**DRGCODES**: ROW_ID, SUBJECT_ID, HADM_ID, DRG_TYPE, DRG_CODE, DESCRIPTION, DRG_SEVERITY, DRG_MORTALITY

**CPTEVENTS**: ROW_ID, SUBJECT_ID, HADM_ID, COSTCENTER, CHARTDATE, CPT_CD, CPT_NUMBER, CPT_SUFFIX, TICKET_ID_SEQ, SECTIONHEADER, SUBSECTIONHEADER, DESCRIPTION

**CAREGIVERS**: ROW_ID, CGID, LABEL, DESCRIPTION

**Dictionary tables**:
- **D_ICD_DIAGNOSES**: ROW_ID, ICD9_CODE, SHORT_TITLE, LONG_TITLE
- **D_ICD_PROCEDURES**: ROW_ID, ICD9_CODE, SHORT_TITLE, LONG_TITLE
- **D_LABITEMS**: ROW_ID, ITEMID, LABEL, FLUID, CATEGORY, LOINC_CODE
- **D_ITEMS**: ROW_ID, ITEMID, LABEL, ABBREVIATION, DBSOURCE, LINKSTO, CATEGORY, UNITNAME, PARAM_TYPE, CONCEPTID
- **D_CPT**: ROW_ID, CATEGORY, SECTIONRANGE, SECTIONHEADER, SUBSECTIONRANGE, SUBSECTIONHEADER, CODESUFFIX, MINCODEINSUBSECTION, MAXCODEINSUBSECTION

### Large tables (slow to scan)

MIMIC-III: CHARTEVENTS, LABEVENTS, INPUTEVENTS_CV, INPUTEVENTS_MV, NOTEEVENTS

MIMIC-IV: chartevents, labevents, inputevents
