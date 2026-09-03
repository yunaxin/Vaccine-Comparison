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


def compare_patient_to_state(patient_ledger: dict, requirement_set: dict, model_used: str = "stub_dose_count_only") -> dict:
    ledger_lookup = build_ledger_lookup(patient_ledger)

    per_disease = []
    for req in requirement_set["requirements"]:
        disease = req["disease"]
        doses_required = req["doses_required"]
        doses_received = ledger_lookup.get(disease, 0)

        status = stub_compliance_check(doses_received, doses_required)

        per_disease.append({
            "disease": disease,
            "doses_required": doses_required,
            "doses_received": doses_received,
            "status": status,
            "notes": req.get("notes"),  # carried through, not evaluated by stub logic
        })

    overall_compliant = all(d["status"] == "met" for d in per_disease)

    return {
        "patient_id": patient_ledger["user_id"],
        "state": requirement_set["state"],
        "model_used": model_used,
        "overall_compliant": overall_compliant,
        "per_disease": per_disease,
    }


def run_comparison(ledger_path: str, requirement_path: str, output_path: str):
    ledgers = load_json(ledger_path)
    requirement_set = load_json(requirement_path)

    if isinstance(ledgers, dict):
        ledgers = [ledgers]  # normalize single-patient case

    results = [compare_patient_to_state(ledger, requirement_set) for ledger in ledgers]

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Compared {len(results)} patient(s) against {requirement_set['state']} requirements")
    for r in results:
        met = sum(1 for d in r["per_disease"] if d["status"] == "met")
        partial = sum(1 for d in r["per_disease"] if d["status"] == "partial")
        missing = sum(1 for d in r["per_disease"] if d["status"] == "missing")
        print(f"  {r['patient_id']}: overall_compliant={r['overall_compliant']} "
              f"({met} met, {partial} partial, {missing} missing)")

    print(f"\nResults written to {output_path}")
    return results


def run_all_comparisons(ledger_path: str, requirements_dir: str, output_dir: str):
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
        all_results[state_name] = run_comparison(ledger_path, str(req_file), output_path)

    print(f"\nDone. Compared against {len(requirement_files)} state(s): "
          f"{[f.stem for f in requirement_files]}")
    return all_results


if __name__ == "__main__":
    run_all_comparisons(
        ledger_path="data/ledgers/my_ledger_output.json",
        requirements_dir="data/state_requirements",
        output_dir="data/comparisons",
    )