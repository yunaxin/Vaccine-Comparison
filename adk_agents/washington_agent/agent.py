"""
agent.py

An ADK (Agent Development Kit) agent that checks a patient's ledger
against Washington state's immunization requirements. Uses two function
tools: one to look up a patient's real dose history by name from the
benchmark dataset, and one to check dose validity against Washington's
rules -- keeping the actual date arithmetic reliable and separate from
the model's own reasoning.
"""

import json
import os
from google.adk import Agent

from .dose_validity_tool import evaluate_dose_series


def lookup_patient_ledger(patient_name: str) -> str:
    """
    Looks up a patient's date of birth and full dose history by name
    from the benchmark patient dataset.

    Args:
        patient_name: the patient's full name as it appears in the
            dataset, e.g. "Reynaldo722 Beatty507"

    Returns:
        A JSON string with the patient's date_of_birth and their doses
        grouped by disease name, or an error message if no patient with
        that name is found.
    """
    data_path = os.path.join(os.path.dirname(__file__), "synthea_ledgers.json")
    with open(data_path) as f:
        ledgers = json.load(f)

    patient = next((p for p in ledgers if p["patient_name"] == patient_name), None)
    if patient is None:
        return json.dumps({"error": f"No patient found named '{patient_name}'"})

    doses_by_disease = {}
    for disease in patient["ledger"]:
        doses_by_disease[disease["disease_name"]] = [
            d["dose_date"] for d in disease["doses_received"]
        ]

    return json.dumps({
        "patient_name": patient["patient_name"],
        "date_of_birth": patient["date_of_birth"],
        "doses_by_disease": doses_by_disease,
    })


def check_disease_compliance(disease_name: str, dose_dates: list, date_of_birth: str) -> str:
    """
    Checks a patient's dose history for one disease against Washington's
    minimum age and minimum interval requirements, returning per-dose
    validity results as a JSON string.

    Args:
        disease_name: the disease to check, e.g. "Polio", "Diphtheria", "Measles"
        dose_dates: list of ISO date strings (YYYY-MM-DD) for doses the
            patient has received for this disease, in chronological order
        date_of_birth: the patient's date of birth as an ISO date string

    Returns:
        A JSON string with per-dose status ("yes", "missing", "eligible",
        or "invalid") and the reasoning for each.
    """
    data_path = os.path.join(os.path.dirname(__file__), "Washington.json")
    with open(data_path) as f:
        wa_requirements = json.load(f)

    matching = [r for r in wa_requirements["requirements"] if r["disease"] == disease_name]
    if not matching:
        return json.dumps({"error": f"No Washington requirement found for disease '{disease_name}'"})

    requirement = matching[0]
    dose_schedule = requirement["dose_schedule"]

    if not dose_schedule:
        return json.dumps({
            "disease": disease_name,
            "not_applicable": True,
            "reason": requirement.get("notes", "Not required for this grade range."),
        })

    results = evaluate_dose_series(dose_schedule, dose_dates, date_of_birth)

    return json.dumps({
        "disease": disease_name,
        "doses_required": requirement["doses_required"],
        "grade_or_age_range": requirement["grade_or_age_range"],
        "state_notes": requirement.get("notes"),
        "per_dose_results": results,
    })


root_agent = Agent(
    name="washington_immunization_checker",
    model="gemini-2.5-flash",
    instruction="""You check whether a student's vaccination record satisfies Washington state's school immunization requirements.

If the user gives you a patient's name instead of dose dates directly:
1. Call lookup_patient_ledger with that name to get their date of birth and dose history.
2. If no patient is found, tell the user clearly and do not proceed.

For each disease covered by Washington's school requirements (Diphtheria, Tetanus, Pertussis, Hepatitis B, Measles, Mumps, Rubella, Polio, Varicella):
1. Call check_disease_compliance with the disease name, the patient's dose dates for that disease (in chronological order), and their date of birth. If the patient has no doses on record for a disease, still call the tool with an empty list so eligibility can be calculated.
2. Read the tool's per-dose results carefully. The tool has already done the date math -- do not recalculate ages or intervals yourself, trust the tool's output.
3. If the tool returns not_applicable, report that disease as not applicable and move on.
4. Read the state_notes field for any dose-reduction exceptions (e.g. "dose 5 not needed if dose 4 given at age 4+ and 6 months after dose 3"). Apply these exceptions yourself by reasoning about the per_dose_results -- the tool does not apply these exceptions automatically, only the base schedule check.
5. Determine an overall status per disease: "met" if all required doses are valid (or a reduction exception applies), "partial" if some doses are valid but not enough, "missing" if none are valid, "needs_review" if the tool's results are ambiguous.
6. Summarize your findings clearly, disease by disease, citing the specific per-dose reasoning the tool provided.

Always call the tools before making any compliance judgment. Never estimate or guess a patient's dose history or dose validity without calling the appropriate tool first.""",
    tools=[lookup_patient_ledger, check_disease_compliance],
)