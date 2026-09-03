"""
model_gemini.py

First real model wired into the comparison pipeline, using Gemini via
Vertex AI (no separate deployment needed, unlike MedGemma which requires
a Model Garden endpoint first). Same output shape as compare.py's stub
(ComparisonResult), so results are directly comparable.

Once MedGemma is deployed to an endpoint, swap the model call in
call_model() for an endpoint.predict() call -- everything else
(prompt building, response parsing, output shape) stays the same.
"""

import json
from vertexai.generative_models import GenerativeModel

MODEL_NAME = "gemini-2.5-flash"  # adjust to whichever Gemini version is available in your project

SYSTEM_INSTRUCTIONS = """You are checking whether a patient's vaccination record satisfies a state's school immunization requirements.

For each requirement in the state's requirement list:
1. Check if the requirement applies to this patient given their grade level (see grade_or_age_range). If not, mark it "not_applicable" and do not evaluate it further.
2. If it applies, calculate the patient's age at the date of each relevant dose (using date_of_birth and each dose_date).
3. Read the notes field carefully -- it may describe alternate, reduced dose counts that are acceptable if specific doses were given at or after a specific age. Apply whichever rule the patient's actual dose ages satisfy, using the MOST FAVORABLE rule that legitimately applies.
4. Assign a status: "met", "partial", "missing", or "not_applicable".
5. Explain your reasoning in the notes field for any case where you applied a conditional/reduced-dose rule rather than just the base dose count.

Do not guess or infer missing dates. If date_of_birth or a dose_date is missing and it's required to evaluate a conditional rule, mark that disease's status as "needs_review" rather than guessing.

Return ONLY a JSON object matching this exact shape, no other text, no markdown formatting:
{
  "patient_id": "...",
  "state": "...",
  "patient_grade_level": "...",
  "model_used": "gemini",
  "overall_compliant": true/false,
  "per_disease": [
    {"disease": "...", "doses_required": N, "doses_received": N, "status": "met|partial|missing|not_applicable|needs_review", "notes": "..."}
  ]
}"""


def clean_json_response(text: str) -> str:
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return text.strip()


def call_model(patient_ledger: dict, requirement_set: dict, patient_grade_level: str) -> dict:
    model = GenerativeModel(MODEL_NAME, system_instruction=SYSTEM_INSTRUCTIONS)

    prompt = f"""Patient ledger:
{json.dumps(patient_ledger, indent=2)}

Patient grade level: {patient_grade_level}

State requirements:
{json.dumps(requirement_set, indent=2)}"""

    response = model.generate_content(prompt)
    cleaned = clean_json_response(response.text)

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"Failed to parse model response as JSON: {e}")
        print(f"Raw response: {response.text[:500]}")
        raise

    return result


def run_model_comparison(ledger_path: str, requirement_path: str, output_path: str, patient_grade_level: str = "K-12", limit: int = None):
    """
    Runs the real model against ledgers, same interface shape as
    compare.py's run_comparison(), for direct output comparison.
    limit: optionally cap how many patients to run (model calls cost
    money/quota -- test on a few before running all 113).
    """
    with open(ledger_path) as f:
        ledgers = json.load(f)
    with open(requirement_path) as f:
        requirement_set = json.load(f)

    if isinstance(ledgers, dict):
        ledgers = [ledgers]
    if limit:
        ledgers = ledgers[:limit]

    results = []
    for i, ledger in enumerate(ledgers):
        print(f"Processing patient {i + 1}/{len(ledgers)}: {ledger.get('patient_name', ledger['user_id'])}")
        try:
            result = call_model(ledger, requirement_set, patient_grade_level)
            results.append(result)
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({"patient_id": ledger["user_id"], "error": str(e)})

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults written to {output_path}")
    return results