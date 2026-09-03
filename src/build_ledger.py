"""
build_ledger.py

Takes cleaned dose records (output of transform.py) and groups them into a
disease-by-disease ledger, using vaccine_mapping.json to know which
disease(s) each vaccine_name prevents and how many doses are expected.

NOW ALSO includes date_of_birth per patient when available (e.g. from
Synthea's patients.csv BIRTHDATE column), so downstream comparison (the
real AI model) can actually evaluate age-conditional requirement rules
instead of marking everything "needs_review".

Usage:
    python3 -m src.build_ledger
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Optional


def load_json(path: str):
    with open(path) as f:
        return json.load(f)


def group_by_disease(dose_records: list, vaccine_mapping: dict):
    by_disease = defaultdict(list)
    unmapped = []

    for record in dose_records:
        vaccine_name = record["vaccine_name"]
        mapping = vaccine_mapping.get(vaccine_name)

        if mapping is None:
            unmapped.append(record)
            continue

        for disease in mapping["diseases_prevented"]:
            by_disease[disease].append({
                "vaccine_name": vaccine_name,
                "dose_date": record["dose_date"],
                "expected_total_doses": mapping.get("expected_total_doses"),
            })

    return by_disease, unmapped


def build_disease_entry(disease_name: str, doses: list) -> dict:
    sorted_doses = sorted(doses, key=lambda d: d["dose_date"])

    doses_received = [
        {
            "dose_label": f"Dose {i + 1}",
            "vaccine_name": d["vaccine_name"],
            "dose_date": d["dose_date"],
        }
        for i, d in enumerate(sorted_doses)
    ]

    doses_completed_count = len(sorted_doses)
    expected_values = [d["expected_total_doses"] for d in sorted_doses if d["expected_total_doses"]]
    doses_expected_count = max(expected_values) if expected_values else None

    if doses_expected_count is None:
        completion_status = "Unknown"
    elif doses_completed_count >= doses_expected_count:
        completion_status = "Complete"
    else:
        completion_status = "Partial"

    missing_doses = []
    if doses_expected_count and doses_completed_count < doses_expected_count:
        missing_doses = [f"Dose {i + 1}" for i in range(doses_completed_count, doses_expected_count)]

    return {
        "disease_name": disease_name,
        "doses_received": doses_received,
        "doses_completed_count": doses_completed_count,
        "doses_expected_count": doses_expected_count,
        "completion_status": completion_status,
        "missing_doses": missing_doses,
    }


def build_patient_ledger(user_id: str, patient_name: str, dose_records: list, vaccine_mapping: dict, date_of_birth: Optional[str] = None) -> dict:
    by_disease, unmapped = group_by_disease(dose_records, vaccine_mapping)

    ledger = [
        build_disease_entry(disease_name, doses)
        for disease_name, doses in sorted(by_disease.items())
    ]

    result = {
        "user_id": user_id,
        "patient_name": patient_name,
        "date_of_birth": date_of_birth,  # NEW -- None if not available, but explicit
        "ledger": ledger,
    }

    if unmapped:
        result["unmapped_records"] = unmapped

    return result


def build_all_ledgers(clean_records_path: str, vaccine_mapping_path: str, output_path: str, dob_lookup: Optional[dict] = None):
    """
    dob_lookup: optional dict of {user_id: "YYYY-MM-DD"}. If provided,
    each patient's date_of_birth is populated from it. If a user_id isn't
    found in dob_lookup, date_of_birth stays None (explicit, not guessed).
    """
    records = load_json(clean_records_path)
    vaccine_mapping = load_json(vaccine_mapping_path)
    dob_lookup = dob_lookup or {}

    by_patient = defaultdict(list)
    patient_names = {}
    for r in records:
        by_patient[r["user_id"]].append(r)
        patient_names[r["user_id"]] = r["patient_name"]

    ledgers = [
        build_patient_ledger(
            user_id,
            patient_names[user_id],
            records,
            vaccine_mapping,
            date_of_birth=dob_lookup.get(user_id),
        )
        for user_id, records in by_patient.items()
    ]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(ledgers, f, indent=2)

    has_dob = sum(1 for l in ledgers if l["date_of_birth"])
    print(f"Built {len(ledgers)} patient ledger(s) -> {output_path}")
    print(f"  {has_dob} of {len(ledgers)} patients have date_of_birth populated")
    for ledger in ledgers:
        unmapped_note = f" ({len(ledger['unmapped_records'])} unmapped vaccines)" if "unmapped_records" in ledger else ""
        dob_note = f", DOB={ledger['date_of_birth']}" if ledger["date_of_birth"] else ", DOB=missing"
        print(f"  {ledger['patient_name']}: {len(ledger['ledger'])} disease groups{unmapped_note}{dob_note}")

    return ledgers


if __name__ == "__main__":
    build_all_ledgers(
        clean_records_path="data/extracted_records_clean.json",
        vaccine_mapping_path="data/vaccine_mapping.json",
        output_path="data/ledgers/my_ledger_output.json",
    )