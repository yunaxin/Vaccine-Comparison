"""
model_palmyra.py

Compares a patient's immunization ledger against a state's requirements
using Writer's Palmyra API.

Requires a Writer API key set as an environment variable:
    WRITER_API_KEY=...

Note: Palmyra X4 (palmyra-x4) is scheduled for deprecation on
November 18, 2026, with Palmyra X5 (palmyra-x5) as the replacement.
MODEL_NAME below can be updated to "palmyra-x5" if needed.
"""

import json
import os
from writerai import Writer

MODEL_NAME = "palmyra-x4"

SYSTEM_INSTRUCTIONS = """You are checking whether a patient's vaccination record satisfies a state's school immunization requirements.

For each requirement in the state's requirement list:
1. Check if the requirement applies to this patient given their grade level (see grade_or_age_range). If not, mark it "not_applicable" and do not evaluate it further.
2. If it applies, calculate the patient's age at the date of each relevant dose (using date_of_birth and each dose_date).
3. Read the notes field carefully -- it may describe alternate, reduced dose counts that are acceptable if specific doses were given at or after a specific age. Apply whichever rule the patient's actual dose ages satisfy, using the MOST FAVORABLE rule that legitimately applies.
4. Assign a status using these exact definitions:
   - "met": doses_received >= doses_required (after applying any conditional reduction from step 3)
   - "partial": doses_received is greater than 0 but less than doses_required
   - "missing": doses_received is exactly 0
   - "not_applicable": the requirement does not apply to this patient's grade/age (per step 1)
   - "needs_review": a required piece of information (date_of_birth, a dose_date) is missing and is necessary to evaluate a conditional rule
5. Verify the status assignment against doses_received and doses_required using the definitions above before finalizing.
6. Explain the reasoning in the notes field for any case where a conditional/reduced-dose rule was applied.

Do not guess or infer missing dates. If date_of_birth or a dose_date is missing and it's required to evaluate a conditional rule, use "needs_review" rather than guessing.

Return ONLY a JSON object matching this exact shape, no other text, no markdown formatting:
{
  "patient_id": "...",
  "state": "...",
  "patient_grade_level": "...",
  "model_used": "palmyra",
  "overall_compliant": true/false,
  "per_disease": [
    {"disease": "...", "doses_required": N, "doses_received": N, "status": "met|partial|missing|not_applicable|needs_review", "notes": "..."}
  ]
}"""

_client = None


def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("WRITER_API_KEY")
        if not api_key:
            raise ValueError("WRITER_API_KEY environment variable not set.")
        _client = Writer(api_key=api_key)
    return _client


def clean_json_response(text: str) -> str:
    text = text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return text.strip()


def call_model(patient_ledger: dict, requirement_set: dict, patient_grade_level: str) -> dict:
    client = get_client()

    prompt = f"""Patient ledger:
{json.dumps(patient_ledger, indent=2)}

Patient grade level: {patient_grade_level}

State requirements:
{json.dumps(requirement_set, indent=2)}"""

    response = client.chat.chat(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": prompt},
        ],
    )

    raw_text = response.choices[0].message.content
    cleaned = clean_json_response(raw_text)

    return json.loads(cleaned)


def run_model_comparison(ledger_path: str, requirement_path: str, output_path: str, patient_grade_level: str = "K-12", limit: int = None):
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