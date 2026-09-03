"""
compare.py

Compares a patient's ledger against a state's requirement set.

This is a STUB implementation: it only compares dose counts, with no
age-adjustment (your ledger doesn't yet track age-at-dose, and your state
requirement data has documented age-conditional exceptions in `notes` that
this logic does NOT evaluate -- see California.json's notes field).

This proves the pipeline shape end-to-end. Once Colab/model access is
ready, `stub_compliance_check()` gets replaced by a real model call that
CAN reason about the age-conditional notes text -- everything else
(loading, output shape, writing results) stays the same.

Usage:
    python3 -m src.compare
"""

import json
from collections import defaultdict
from pathlib import Path


def load_json(path: str):
    with open(path) as f:
        return json.load(f)


def requirement_applies(grade_or_age_range: str, patient_grade_level: str) -> bool:
    """
    Decides whether a requirement applies to this patient, based on the
    requirement's grade_or_age_range text and the patient's actual grade level.

    patient_grade_level should be one of:
        "pre-k", "TK", "K", "1".."12"

    This is deliberately simple keyword matching, not a full parser --
    good enough for the grade_or_age_range values currently in use
    ("TK/K-12", "Pre-Kindergarten only", "7th-12th grade"). Extend this
    if new phrasing shows up in other states' requirement files.
    """
    range_text = grade_or_age_range.lower()

    if "pre-kindergarten only" in range_text or "pre-k only" in range_text:
        return patient_grade_level.lower() in ("pre-k", "prek")

    if "7th" in range_text and ("12th" in range_text or "-12" in range_text):
        grade_order = ["pre-k", "tk", "k", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
        try:
            patient_index = grade_order.index(patient_grade_level.lower())
            seventh_index = grade_order.index("7")
            return patient_index >= seventh_index
        except ValueError:
            return True  # unrecognized grade format -- don't silently skip, flag via inclusion

    if "tk/k-12" in range_text or "k-12" in range_text:
        return True  # applies to everyone in the TK-12 range

    return True  # unrecognized range text -- default to including it, don't silently drop


def build_ledger_lookup(patient_ledger: dict) -> dict:
    """disease_name -> doses_completed_count, from one patient's ledger."""
    return {
        entry["disease_name"]: entry["doses_completed_count"]
        for entry in patient_ledger["ledger"]
    }


def stub_compliance_check(doses_received: int, doses_required: int) -> str:
    """
    Plain dose-count comparison. NOT age-adjusted.
    Real model logic will need to read the `notes` field to handle
    age-conditional reductions (e.g. "3 doses OK if given after age 4").
    """
    if doses_received >= doses_required:
        return "met"
    elif doses_received > 0:
        return "partial"
    else:
        return "missing"


def compare_patient_to_state(patient_ledger: dict, requirement_set: dict, patient_grade_level: str, model_used: str = "stub_dose_count_only") -> dict:
    ledger_lookup = build_ledger_lookup(patient_ledger)

    per_disease = []
    for req in requirement_set["requirements"]:
        disease = req["disease"]
        doses_required = req["doses_required"]
        grade_range = req["grade_or_age_range"]

        if not requirement_applies(grade_range, patient_grade_level):
            per_disease.append({
                "disease": disease,
                "doses_required": doses_required,
                "doses_received": None,
                "status": "not_applicable",
                "notes": f"Requirement applies to {grade_range}; patient grade level is {patient_grade_level}",
            })
            continue

        doses_received = ledger_lookup.get(disease, 0)
        status = stub_compliance_check(doses_received, doses_required)

        per_disease.append({
            "disease": disease,
            "doses_required": doses_required,
            "doses_received": doses_received,
            "status": status,
            "notes": req.get("notes"),  # carried through, not evaluated by stub logic
        })

    applicable = [d for d in per_disease if d["status"] != "not_applicable"]
    overall_compliant = all(d["status"] == "met" for d in applicable) if applicable else None

    return {
        "patient_id": patient_ledger["user_id"],
        "state": requirement_set["state"],
        "patient_grade_level": patient_grade_level,
        "model_used": model_used,
        "overall_compliant": overall_compliant,
        "per_disease": per_disease,
    }


def run_comparison(ledger_path: str, requirement_path: str, output_path: str, patient_grade_level: str = "K-12"):
    ledgers = load_json(ledger_path)
    requirement_set = load_json(requirement_path)

    if isinstance(ledgers, dict):
        ledgers = [ledgers]  # normalize single-patient case

    results = [compare_patient_to_state(ledger, requirement_set, patient_grade_level) for ledger in ledgers]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Compared {len(results)} patient(s) against {requirement_set['state']} requirements (grade level: {patient_grade_level})")
    for r in results:
        met = sum(1 for d in r["per_disease"] if d["status"] == "met")
        partial = sum(1 for d in r["per_disease"] if d["status"] == "partial")
        missing = sum(1 for d in r["per_disease"] if d["status"] == "missing")
        na = sum(1 for d in r["per_disease"] if d["status"] == "not_applicable")
        print(f"  {r['patient_id']}: overall_compliant={r['overall_compliant']} "
              f"({met} met, {partial} partial, {missing} missing, {na} not_applicable)")

    print(f"\nResults written to {output_path}")
    return results


def run_all_comparisons(ledger_path: str, requirements_dir: str, output_dir: str, patient_grade_level: str = "K-12"):
    """
    Runs the same patient ledger(s) against every state requirement JSON file
    found in requirements_dir. Adding a new state = dropping a new
    <StateName>.json file into that folder, no code changes needed.
    """
    requirement_files = sorted(Path(requirements_dir).glob("*.json"))

    if not requirement_files:
        print(f"No requirement JSON files found in {requirements_dir}")
        return {}

    all_results = {}
    for req_file in requirement_files:
        state_name = req_file.stem
        output_path = str(Path(output_dir) / f"{state_name.lower()}_results.json")
        print(f"\n--- {state_name} ---")
        all_results[state_name] = run_comparison(ledger_path, str(req_file), output_path, patient_grade_level)

    print(f"\nDone. Compared against {len(requirement_files)} state(s): "
          f"{[f.stem for f in requirement_files]}")
    return all_results


if __name__ == "__main__":
    run_all_comparisons(
        ledger_path="data/ledgers/my_ledger_output.json",
        requirements_dir="data/state_requirements",
        output_dir="data/comparisons",
        patient_grade_level="K-12",  # NOTE: your ledger data doesn't track grade yet --
                                      # this is a placeholder until patient profile data
                                      # (date_of_birth, institution_type) exists, per the
                                      # original design doc's Patient Profile section.
    )