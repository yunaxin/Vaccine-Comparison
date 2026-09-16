"""
dose_validity_tool.py

A deterministic tool for checking whether a specific vaccine dose is valid
against a state's minimum age and minimum interval rules. Meant to be
called by an AI agent (via function calling / tool use) rather than
having the model calculate date arithmetic itself -- this fixes the
inconsistency seen in earlier testing where models sometimes handled
age boundaries differently across runs, since there was no reliable
"today's date" reference or guaranteed-correct date math.

The agent still does the real reasoning: deciding which doses to check,
interpreting results, applying reduction exceptions from notes text, and
writing the final explanation. This tool only answers one narrow,
mechanical question per call: "is this specific dose valid?"
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
) -> dict:
    """
    Checks whether a single administered dose meets minimum age and
    minimum interval requirements.

    Returns:
        {
            "valid": bool,
            "reason": str,
            "age_at_dose_days": int,
        }
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

    if additional_constraint is not None:
        # e.g. Hepatitis B dose 3: must also be >=16 weeks after dose 1,
        # not just >=8 weeks after dose 2. Caller supplies the relevant
        # earlier dose date via additional_constraint["reference_date"].
        reference_date = additional_constraint.get("reference_date")
        required_days = additional_constraint.get("days")
        if reference_date and required_days:
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
    today: str = None,
) -> dict:
    """
    For a dose the patient has NOT yet received, determines the earliest
    date they become eligible for it, and whether that date has already
    passed (overdue / "missing") or is still upcoming ("eligible").

    Returns:
        {
            "status": "eligible" | "missing",
            "earliest_eligible_date": str (ISO date),
            "reason": str,
        }
    """
    if today is None:
        today = date.today().isoformat()

    age_based_date = add_days(date_of_birth, minimum_age_days)

    if minimum_interval_days is not None and previous_dose_date is not None:
        interval_based_date = add_days(previous_dose_date, minimum_interval_days)
        earliest_eligible_date = max(age_based_date, interval_based_date)
    else:
        earliest_eligible_date = age_based_date

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
    Evaluates a full dose series (e.g. all 5 DTaP doses) against a
    patient's actual recorded doses, following the same pattern shown in
    the reference UI: each dose is checked in order, and once a dose is
    missing, later doses in the series show as "missing" (dependent on
    the missing one) rather than being independently evaluated.

    patient_doses: list of ISO date strings, in chronological order,
    matching this vaccine (e.g. all DTaP dose dates for one patient).

    Returns a list of per-dose results matching the reference UI's
    Match column: {"dose": N, "status": "yes"|"missing"|"eligible", "reason": str}
    """
    results = []
    previous_dose_date = None

    for i, schedule_entry in enumerate(dose_schedule):
        dose_number = schedule_entry["dose"]
        min_age_days = schedule_entry["minimum_age_days"]
        min_interval_days = schedule_entry.get("minimum_interval_days")

        if i < len(patient_doses):
            # patient has a recorded dose at this position
            dose_date = patient_doses[i]
            check = check_dose_validity(
                dose_date=dose_date,
                date_of_birth=date_of_birth,
                minimum_age_days=min_age_days,
                minimum_interval_days=min_interval_days,
                previous_dose_date=previous_dose_date,
            )
            results.append({
                "dose": dose_number,
                "status": "yes" if check["valid"] else "invalid",
                "reason": check["reason"],
                "date": dose_date,
            })
            previous_dose_date = dose_date

        else:
            # no recorded dose at this position -- check if this is the
            # immediate next dose (previous one exists/valid) or a
            # further-out one that depends on an earlier missing dose
            if i == 0 or (results and results[-1]["status"] == "yes"):
                eligibility = check_next_dose_eligibility(
                    date_of_birth=date_of_birth,
                    minimum_age_days=min_age_days,
                    minimum_interval_days=min_interval_days,
                    previous_dose_date=previous_dose_date,
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