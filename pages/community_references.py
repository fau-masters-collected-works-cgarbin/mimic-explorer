"""Community References: links to existing MIMIC resources."""

import streamlit as st

st.title("Community References")

st.markdown(
    "The MIMIC ecosystem has established resources for different stages of "
    "your work. This page points you to the right one for what you need."
)

st.info(
    "**Where to start.** "
    "For hands-on practice, open the "
    "[Google Colab notebook](https://colab.research.google.com/drive/"
    "1REu-ofzNzqsTT1cxLHIegPB0nGmwKaM0). "
    "When you need to look up what a column means, use "
    "[mimic.mit.edu](https://mimic.mit.edu/docs/iv/). "
    "When you're computing a clinical concept (severity scores, sepsis "
    "criteria, ventilation duration), check "
    "[mimic-code](https://github.com/MIT-LCP/mimic-code/tree/main/"
    "mimic-iv/concepts) before writing your own SQL."
)

st.subheader("Official Documentation")

st.markdown("""
[mimic.mit.edu](https://mimic.mit.edu/docs/) is the authoritative
reference for both MIMIC-III and MIMIC-IV. Each table has its own page
with column names, types, and descriptions. Start here when you need to
understand what a specific column means or what values it can take.
The [MIMIC-III tables](https://mimic.mit.edu/docs/iii/tables/) and
[MIMIC-IV modules](https://mimic.mit.edu/docs/iv/modules/) are the
most useful entry points.
""")

st.subheader("Schema Diagrams")

st.markdown("""
[SchemaSpy](https://lcp.mit.edu/mimic-schema-spy/) is an interactive
schema browser generated from a PostgreSQL load of MIMIC-III (2017). It
has clickable tables, foreign key diagrams, and column-level metadata.
It's the most detailed relationship view available, though it covers
MIMIC-III only. Community-contributed ER diagrams are also collected in
[mimic-code#183](https://github.com/MIT-LCP/mimic-code/issues/183),
and the MIMIC-IV
[Scientific Data paper](https://www.nature.com/articles/s41597-022-01899-x)
includes schema figures.
""")

st.subheader("Derived Concepts (mimic-code)")

st.markdown("""
[mimic-code](https://github.com/MIT-LCP/mimic-code) is the official
community repository maintained by MIT-LCP. Its most valuable part for
researchers is the
[derived concepts SQL](https://github.com/MIT-LCP/mimic-code/tree/main/mimic-iv/concepts),
which encodes the community's collective knowledge of what's clinically
meaningful: severity scores (SOFA, SAPS, OASIS), ventilation duration,
fluid balance, first-day labs, sepsis criteria, and more. If you're
computing a clinical concept, check here before writing your own SQL.
The repo also contains PostgreSQL and BigQuery build scripts.
""")

st.subheader("Tutorials and Workshops")

st.markdown("""
Alistair Johnson (lead MIMIC developer) has a
[data tutorial](https://alistairewj.github.io/talk/2020-mimic-iv-data-tutorial/)
covering what information MIMIC-IV contains and an
[analysis tutorial](https://alistairewj.github.io/talk/2020-mimic-iv-analysis-tutorial/)
walking through hypothesis formulation to reproducible study design.
A [Google Colab notebook](https://colab.research.google.com/drive/1REu-ofzNzqsTT1cxLHIegPB0nGmwKaM0)
provides a hands-on introduction, and
[mimic-workshop](https://github.com/MIT-LCP/mimic-workshop) has
materials from datathons and workshops.
""")

st.subheader("BigQuery Access")

st.markdown("""
MIMIC-IV is available on Google BigQuery
(`physionet-data.mimiciv_hosp`, `physionet-data.mimiciv_icu`, etc.)
for credentialed researchers. BigQuery provides a browser-based SQL
editor with schema browsing and data preview. It's the fastest way to
run ad-hoc queries without a local database, though it requires GCP
access and PhysioNet credentialing.
""")

st.subheader("MIMIC-IV Demo")

st.markdown("""
[MIMIC-IV Demo](https://physionet.org/content/mimic-iv-demo/2.2/) is a
small, freely accessible subset of MIMIC-IV that requires no
credentialing. It's useful for testing code, building tutorials, or
getting a feel for the data structure before applying for full access.
""")

st.subheader("FHIR Mapping")

st.markdown("""
The [MIMIC FHIR Implementation Guide](https://mimic.mit.edu/fhir/)
maps MIMIC-IV columns to FHIR resources. If you're working with
healthcare interoperability standards or want to understand the semantic
meaning of columns in a standardized vocabulary, this is the reference.
""")
