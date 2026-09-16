"""
app.py

Streamlit app for looking up a patient's compliance against Washington's
school immunization requirements. Directly imports dose_validity_tool.py
and reads the real Washington.json and synthea_ledgers.json data files --
no duplicated logic, unlike the standalone HTML/JS version.

Run with:
    streamlit run app.py
"""

import json
import streamlit as st
from datetime import date

from src.dose_validity_tool import evaluate_disease_compliance

st.set_page_config(page_title="Washington Immunization Record Lookup", page_icon="🩺", layout="centered")


@st.cache_data
def load_requirements():
    with open("data/state_requirements/Washington.json") as f:
        data = json.load(f)
    return {r["disease"]: r for r in data["requirements"]}


@st.cache_data
def load_patients():
    with open("data/synthea_ledgers.json") as f:
        ledgers = json.load(f)
    patients = {}
    for p in ledgers:
        doses_by_disease = {
            disease["disease_name"]: [d["dose_date"] for d in disease["doses_received"]]
            for disease in p["ledger"]
        }
        patients[p["patient_name"]] = {"dob": p["date_of_birth"], "doses": doses_by_disease}
    return patients


REQUIREMENTS = load_requirements()
PATIENTS = load_patients()

SCHOOL_DISEASES = [
    "Diphtheria", "Tetanus", "Pertussis", "Hepatitis B",
    "Measles", "Mumps", "Rubella", "Polio", "Varicella",
]

STATUS_COLORS = {"met": "green", "partial": "orange", "missing": "red", "not_applicable": "gray"}

st.title("Immunization Record Lookup")
st.caption("A dose-by-dose record check against Washington's school entry rules.")

patient_name = st.selectbox("Select a patient", options=[""] + sorted(PATIENTS.keys()))

if patient_name:
    patient = PATIENTS[patient_name]
    dob = patient["dob"]
    age_years = (date.today() - date.fromisoformat(dob)).days // 365
    today = date.today().isoformat()

    st.divider()
    col1, col2, col3 = st.columns(3)
    col1.metric("Date of birth", dob)
    col2.metric("Age", f"{age_years} yrs")
    col3.metric("Grade range checked", "K-12")

    results = []
    for disease in SCHOOL_DISEASES:
        requirement = REQUIREMENTS.get(disease)
        if requirement is None:
            continue
        doses = patient["doses"].get(disease, [])
        result = evaluate_disease_compliance(requirement, doses, dob, today=today)
        results.append(result)

    met_count = sum(1 for r in results if r.get("overall_status") == "met")
    partial_count = sum(1 for r in results if r.get("overall_status") == "partial")
    missing_count = sum(1 for r in results if r.get("overall_status") == "missing")

    if partial_count == 0 and missing_count == 0:
        st.success(f"All {met_count} checked diseases: **Met**. This record satisfies Washington's school entry requirements for every disease checked.")
    else:
        st.warning(f"**{met_count} met, {partial_count} partial, {missing_count} missing.** See below for which doses are needed to complete each series.")

    st.divider()

    for result in results:
        with st.container(border=True):
            header_col, status_col = st.columns([4, 1])
            header_col.subheader(result["disease"])
            status = result.get("overall_status", "not_applicable")
            status_col.markdown(f":{STATUS_COLORS.get(status, 'gray')}[**{status.upper()}**]")

            if result.get("not_applicable"):
                st.caption(result["reason"])
                continue

            table_rows = []
            schedule_by_dose = {s["dose"]: s for s in REQUIREMENTS[result["disease"]]["dose_schedule"]}
            for dose_result in result["per_dose_results"]:
                schedule_entry = schedule_by_dose.get(dose_result["dose"], {})
                table_rows.append({
                    "Dose": dose_result["dose"],
                    "Requirement": schedule_entry.get("minimum_interval_from_previous") or schedule_entry.get("minimum_age", ""),
                    "On record": dose_result["date"] or "—",
                    "Result": dose_result["status"].capitalize(),
                })
            st.table(table_rows)

            if result.get("reduction_applied"):
                st.caption(f"⚠️ {result['reduction_applied']}")
            st.caption(f"**Washington requirement.** {result['state_notes']}")

    st.divider()
    st.caption(
        "Computed using Washington DOH-348-284 (Feb 2026) dose-schedule data and the same "
        "deterministic date-validity logic used by the Washington immunization compliance agent. "
        "This is not medical advice; consult a licensed provider or the school's health office "
        "for official determinations."
    )