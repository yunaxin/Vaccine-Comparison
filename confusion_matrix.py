"""
confusion_matrix.py

Builds a real confusion matrix for Gemini and Llama 4 against a verified
ground truth, computed deterministically by dose_validity_tool.py.

Matching is keyed by (patient_id, disease) only. An earlier version also
required doses_required to match exactly, which broke whenever a model
correctly reported a reduced dose count after applying an exception
(e.g. reporting 4 required instead of the base 5) -- the model wasn't
wrong, the key was just too strict to recognize it as the same check.

California has two separate Pertussis requirements: the base 5-dose K-12
series and a separate 1-dose 7th-grade Tdap booster. Both are correctly
reported as distinct entries by the models. The booster is excluded
entirely from ground truth (see EXCLUDED_FROM_SCORING, since it depends
on real grade data this project doesn't track) and its matching entry
in each model's output is identified by doses_required == 1 and
excluded the same way, so only the base-series Pertussis entry is ever
indexed under the "Pertussis" key on either side.

Usage:
    python3 -m confusion_matrix
"""

import json
from collections import defaultdict

from src.dose_validity_tool import evaluate_disease_compliance

EXCLUDED_FROM_SCORING = {
    ("Pertussis", "7th-12th grade"),
}

PERTUSSIS_BOOSTER_DOSES_REQUIRED = 1


def load_json(path):
    with open(path) as f:
        return json.load(f)


def build_ground_truth(ledger_path, requirements_path, patient_ids, today=None):
    ledgers = load_json(ledger_path)
    all_requirements = load_json(requirements_path)["requirements"]
    ledgers_by_id = {p["user_id"]: p for p in ledgers}

    ground_truth = {}
    excluded_count = 0

    for patient_id in patient_ids:
        patient = ledgers_by_id.get(patient_id)
        if patient is None:
            continue
        doses_by_disease = {
            d["disease_name"]: [x["dose_date"] for x in d["doses_received"]]
            for d in patient["ledger"]
        }
        for requirement in all_requirements:
            disease = requirement["disease"]
            grade_range = requirement.get("grade_or_age_range", "")

            if (disease, grade_range) in EXCLUDED_FROM_SCORING:
                excluded_count += 1
                continue

            doses = doses_by_disease.get(disease, [])
            result = evaluate_disease_compliance(requirement, doses, patient["date_of_birth"], today=today)
            status = "not_applicable" if result.get("not_applicable") else result["overall_status"]
            ground_truth[(patient_id, disease)] = status

    return ground_truth, excluded_count


def index_model_results(results_path):
    results = load_json(results_path)
    index = {}
    skipped_booster_count = 0
    for patient_result in results:
        if "error" in patient_result:
            continue
        patient_id = patient_result.get("patient_id")
        for disease_result in patient_result.get("per_disease", []):
            if (disease_result["disease"] == "Pertussis"
                    and disease_result.get("doses_required") == PERTUSSIS_BOOSTER_DOSES_REQUIRED):
                skipped_booster_count += 1
                continue
            key = (patient_id, disease_result["disease"])
            index[key] = disease_result["status"]
    return index, skipped_booster_count


def compute_confusion_matrix(ground_truth, model_predictions, model_name):
    matrix = defaultdict(lambda: defaultdict(int))
    correct = 0
    total = 0
    disagreements = []
    unmatched_ground_truth = 0

    for key, true_status in ground_truth.items():
        if key not in model_predictions:
            unmatched_ground_truth += 1
            continue
        predicted_status = model_predictions[key]
        matrix[true_status][predicted_status] += 1
        total += 1
        if predicted_status == true_status:
            correct += 1
        else:
            disagreements.append((key, true_status, predicted_status))

    accuracy = correct / total if total else 0

    print(f"\n=== {model_name} vs. ground truth ===")
    print(f"Compared {total} disease-checks ({unmatched_ground_truth} ground-truth entries had no matching model prediction)")
    print(f"Accuracy: {accuracy:.1%} ({correct}/{total})\n")

    statuses = sorted(set(matrix.keys()) | {s for row in matrix.values() for s in row.keys()})
    header = "Truth \\ Predicted".ljust(20) + "".join(s.ljust(16) for s in statuses)
    print(header)
    for true_status in statuses:
        row = true_status.ljust(20)
        for predicted_status in statuses:
            row += str(matrix[true_status][predicted_status]).ljust(16)
        print(row)

    print(f"\n--- Per-class precision / recall / F1 ---")
    for status in statuses:
        tp = matrix[status][status]
        fp = sum(matrix[other][status] for other in statuses if other != status)
        fn = sum(matrix[status][other] for other in statuses if other != status)
        precision = tp / (tp + fp) if (tp + fp) else 0
        recall = tp / (tp + fn) if (tp + fn) else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0
        print(f"  {status.ljust(16)} precision={precision:.1%}  recall={recall:.1%}  f1={f1:.1%}")

    print(f"\n{len(disagreements)} disagreements. First 10:")
    for (patient_id, disease), true_status, predicted_status in disagreements[:10]:
        print(f"  {patient_id[:12]}... / {disease}: truth={true_status}, {model_name}={predicted_status}")

    return matrix, accuracy


if __name__ == "__main__":
    gemini_predictions, gemini_skipped = index_model_results("data/comparisons/BENCHMARK_gemini_california_50.json")
    llama4_predictions, llama4_skipped = index_model_results("data/comparisons/BENCHMARK_llama4_california_50.json")

    print(f"Skipped {gemini_skipped} Gemini and {llama4_skipped} Llama4 Pertussis-booster entries during indexing.")

    patient_ids = {pid for (pid, _) in gemini_predictions.keys()} | {pid for (pid, _) in llama4_predictions.keys()}

    ground_truth, excluded_count = build_ground_truth(
        ledger_path="data/synthea_ledgers.json",
        requirements_path="data/state_requirements/California.json",
        patient_ids=patient_ids,
    )
    print(f"Excluded {excluded_count} grade-dependent Pertussis-booster checks from ground truth (no real grade data available).")

    compute_confusion_matrix(ground_truth, gemini_predictions, "Gemini")
    compute_confusion_matrix(ground_truth, llama4_predictions, "Llama4")