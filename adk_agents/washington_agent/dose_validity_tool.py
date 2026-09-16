"""
dose_validity_tool.py

A deterministic tool for checking whether a specific vaccine dose is valid
against a state's minimum age and minimum interval rules. Meant to be
called by an AI agent (via function calling / tool use) rather than
having the model calculate date arithmetic itself.

The agent still does the real reasoning: deciding which doses to check,
interpreting results, applying reduction exceptions from notes text, and
writing the final explanation. This tool only answers one narrow,
mechanical question per call: "is this specific dose valid?" or "when
does this dose become eligible?"
"""

from datetime import date, timedelta


def days_between(start: str, end: str) -> int:
    """Returns the number of days between two ISO date strings (end - start)."""
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    return (end_date - start_date).days


def add_days(start: str, days: int) -> str:
    """Returns an ISO date string, `days` after `start`."""
    return (date.fromisoformat(start) + timedelta(days=days)).isoformat()


def check_dose_validity(
    dose_date: str,
    date_of_birth: str,
    minimum_age_days: int,
    minimum_interval_days: int = None,
    previous_dose_date: str = None,
    additional_constraint: dict = None,
    all_patient_doses: list = None,
) -> dict:
    """
    Checks whether a single administered dose meets minimum age and
    minimum interval requirements, including any compound additional
    constraint (e.g. Hepatitis B dose 3 needing both >=8 weeks after
    dose 2 AND >=16 weeks after dose 1).
    """
    age_at_dose_days = days_between(date_of_birth, dose_date)

    if age_at_dose_days < minimum_age_days:
        return {
            "valid": False,
            "reason": f"Given at age {age_at_dose_days} days, below the minimum age of {minimum_age_days} days.",
            "age_at_dose_days": age_at_dose_days,
        }

    if minimum_interval_days is not None and previous_dose_date is not None:
        interval_days = days_between(previous_dose_date, dose_date)
        if interval_days < minimum_interval_days:
            return {
                "valid": False,
                "reason": f"Given {interval_days} days after the previous dose, below the minimum interval of {minimum_interval_days} days.",
                "age_at_dose_days": age_at_dose_days,
            }

    if additional_constraint is not None and all_patient_doses is not None:
        ref_dose_index = additional_constraint.get("days_after_dose", 1) - 1
        required_days = additional_constraint.get("days")
        if ref_dose_index < len(all_patient_doses) and required_days is not None:
            reference_date = all_patient_doses[ref_dose_index]
            gap = days_between(reference_date, dose_date)
            if gap < required_days:
                return {
                    "valid": False,
                    "reason": f"Does not meet the additional constraint: {additional_constraint.get('description', 'extra interval requirement')}.",
                    "age_at_dose_days": age_at_dose_days,
                }

    return {
        "valid": True,
        "reason": "Meets minimum age and interval requirements.",
        "age_at_dose_days": age_at_dose_days,
    }


def check_next_dose_eligibility(
    date_of_birth: str,
    minimum_age_days: int,
    minimum_interval_days: int = None,
    previous_dose_date: str = None,
    additional_constraint: dict = None,
    all_patient_doses: list = None,
    today: str = None,
) -> dict:
    """
    For a dose the patient has NOT yet received, determines the earliest
    date they become eligible for it, and whether that date has already
    passed (overdue / "missing") or is still upcoming ("eligible").

    Correctly accounts for compound additional constraints (e.g.
    Hepatitis B dose 3's "8 weeks after dose 2 AND 16 weeks after dose 1"
    rule) by taking the LATEST of all applicable constraint dates -- a
    fix for a bug where this constraint was previously only applied when
    checking an already-given dose, not when calculating eligibility for
    a dose not yet given.
    """
    if today is None:
        today = date.today().isoformat()

    candidate_dates = [add_days(date_of_birth, minimum_age_days)]

    if minimum_interval_days is not None and previous_dose_date is not None:
        candidate_dates.append(add_days(previous_dose_date, minimum_interval_days))

    if additional_constraint is not None and all_patient_doses is not None:
        ref_dose_index = additional_constraint.get("days_after_dose", 1) - 1
        required_days = additional_constraint.get("days")
        if ref_dose_index < len(all_patient_doses) and required_days is not None:
            reference_date = all_patient_doses[ref_dose_index]
            candidate_dates.append(add_days(reference_date, required_days))

    earliest_eligible_date = max(candidate_dates)

    if earliest_eligible_date > today:
        return {
            "status": "eligible",
            "earliest_eligible_date": earliest_eligible_date,
            "reason": f"Not yet eligible; earliest valid date is {earliest_eligible_date}.",
        }
    else:
        return {
            "status": "missing",
            "earliest_eligible_date": earliest_eligible_date,
            "reason": f"Eligible since {earliest_eligible_date} but no dose on record.",
        }


def evaluate_dose_series(dose_schedule: list, patient_doses: list, date_of_birth: str, today: str = None) -> list:
    """
    Evaluates a full dose series against a patient's actual recorded
    doses, following the reference UI pattern: each dose checked in
    order, later doses depending on earlier ones being present.

    patient_doses: list of ISO date strings, in chronological order.
    """
    results = []
    previous_dose_date = None

    for i, schedule_entry in enumerate(dose_schedule):
        dose_number = schedule_entry["dose"]
        min_age_days = schedule_entry["minimum_age_days"]
        min_interval_days = schedule_entry.get("minimum_interval_days")
        additional_constraint = schedule_entry.get("additional_constraint")

        if i < len(patient_doses):
            dose_date = patient_doses[i]
            check = check_dose_validity(
                dose_date=dose_date,
                date_of_birth=date_of_birth,
                minimum_age_days=min_age_days,
                minimum_interval_days=min_interval_days,
                previous_dose_date=previous_dose_date,
                additional_constraint=additional_constraint,
                all_patient_doses=patient_doses,
            )
            results.append({
                "dose": dose_number,
                "status": "yes" if check["valid"] else "invalid",
                "reason": check["reason"],
                "date": dose_date,
            })
            previous_dose_date = dose_date

        else:
            if i == 0 or (results and results[-1]["status"] == "yes"):
                eligibility = check_next_dose_eligibility(
                    date_of_birth=date_of_birth,
                    minimum_age_days=min_age_days,
                    minimum_interval_days=min_interval_days,
                    previous_dose_date=previous_dose_date,
                    additional_constraint=additional_constraint,
                    all_patient_doses=patient_doses,
                    today=today,
                )
                results.append({
                    "dose": dose_number,
                    "status": eligibility["status"],
                    "reason": eligibility["reason"],
                    "date": None,
                })
            else:
                prior_dose_number = dose_schedule[i - 1]["dose"]
                results.append({
                    "dose": dose_number,
                    "status": "missing",
                    "reason": f"Dose {prior_dose_number} must be administered before dose {dose_number} can become eligible.",
                    "date": None,
                })

    return results