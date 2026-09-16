"""
dose_validity_tool.py

A deterministic tool for checking whether a specific vaccine dose is valid
against a state's minimum age and minimum interval rules, and for
evaluating a patient's overall compliance for one disease, including
dose-reduction exceptions. This is the single shared implementation used
by both the ADK agent's tool function and any other interface (e.g. a
Streamlit app) built on top of it.
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
    Accounts for compound additional constraints by taking the LATEST of
    all applicable constraint dates.
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
    doses: each dose checked in order, later doses depending on earlier
    ones being present. patient_doses: list of ISO date strings, in
    chronological order.
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


def reduction_applies(patient_doses: list, date_of_birth: str, reduction: dict) -> bool:
    """
    Checks whether a dose-reduction exception applies (e.g. DTaP dose 5
    not needed if dose 4 was given at age 4+ and >=6 months after dose 3).
    """
    trigger_idx = reduction["trigger_dose_index"]
    prev_idx = reduction["prev_dose_index"]
    if len(patient_doses) <= trigger_idx:
        return False
    trigger_date = patient_doses[trigger_idx]
    prev_date = patient_doses[prev_idx]
    age_at_trigger = days_between(date_of_birth, trigger_date)
    interval_from_prev = days_between(prev_date, trigger_date)
    return age_at_trigger >= reduction["min_age_days"] and interval_from_prev >= reduction["min_interval_days"]


def evaluate_disease_compliance(requirement: dict, patient_doses: list, date_of_birth: str, today: str = None) -> dict:
    """
    The single, shared entry point for checking one disease's compliance.
    Used identically by the ADK agent's tool function and by any other
    interface built on top of this module.
    """
    dose_schedule = requirement.get("dose_schedule", [])

    if not dose_schedule:
        return {
            "disease": requirement["disease"],
            "not_applicable": True,
            "reason": requirement.get("notes", "Not required for this grade range."),
        }

    patient_doses = sorted(patient_doses)
    results = evaluate_dose_series(dose_schedule, patient_doses, date_of_birth, today=today)

    effective_required = requirement["doses_required"]
    reduction = requirement.get("reduction")
    reduction_note = None
    if reduction and reduction_applies(patient_doses, date_of_birth, reduction):
        effective_required = reduction["reduces_to"]
        results = [r for r in results if r["dose"] <= effective_required or r["status"] == "yes"]
        reduction_note = f"Reduction exception applied: only {effective_required} doses required based on dose {reduction['trigger_dose_index'] + 1}'s age and timing."

    valid_count = sum(1 for r in results if r["status"] == "yes")
    if valid_count >= effective_required:
        overall = "met"
    elif valid_count > 0:
        overall = "partial"
    else:
        overall = "missing"

    return {
        "disease": requirement["disease"],
        "doses_required": requirement["doses_required"],
        "effective_doses_required": effective_required,
        "grade_or_age_range": requirement["grade_or_age_range"],
        "state_notes": requirement.get("notes"),
        "reduction_applied": reduction_note,
        "overall_status": overall,
        "per_dose_results": results,
    }