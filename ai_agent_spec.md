# AI Agent Spec: Ledger-to-State-Requirement Compliance Comparison

## Purpose
Given one patient's immunization ledger and one state's structured immunization
requirements, determine the patient's compliance status per disease --
including cases dose-count-only logic cannot handle: age-conditional dose
reductions, grade-specific booster rules, and requirements that don't apply
to the patient's grade/age at all.

## The problem with dose counting alone
Real state requirements have conditional logic written into free text, e.g.:
  "5 doses meet requirement, OR 4 if >=1 dose given at age >=4 years,
   OR 3 if >=1 Tdap dose given at age >=7 years"
A fixed dose-count comparison can't apply a rule like this correctly --
it would need to know the patient's age at each dose and pick the right
threshold. Hardcoding every state's version of this rule into Python gets
brittle fast, since each state phrases these conditions differently. This
is the part of the task handed off to a model instead.

## Inputs the agent receives

**1. Patient ledger** (matches `PatientLedger` in schema.py):
```json
{
  "user_id": "user_001",
  "patient_name": "...",
  "date_of_birth": "YYYY-MM-DD",
  "ledger": [
    {
      "disease_name": "Pertussis",
      "doses_received": [
        {"dose_label": "Dose 1", "vaccine_name": "DTaP", "dose_date": "2018-02-28"}
      ],
      "doses_completed_count": 4
    }
  ]
}
```

**2. State requirement set** (matches `StateRequirementSet` in schema.py):
```json
{
  "state": "California",
  "requirements": [
    {
      "disease": "Pertussis",
      "doses_required": 5,
      "grade_or_age_range": "TK/K-12",
      "notes": "5 doses meet requirement, OR 4 if >=1 dose at age>=4, OR 3 if >=1 Tdap dose at age>=7."
    }
  ]
}
```

**3. Patient grade level** -- currently passed as a fixed string
(e.g. `"K-12"`) at call time. See Known Gaps below.

## Task instructions given to every model

Every model integration in this repo uses the same instructions, so
differences in output reflect differences in model reasoning rather than
differences in what was asked:

1. Check if a requirement applies to the patient's grade level. If not,
   mark `not_applicable` and stop evaluating that requirement.
2. Calculate the patient's age at each relevant dose date.
3. Apply any conditional/reduced-dose rule in the requirement's `notes`
   field that the patient's dose ages satisfy, using the most favorable
   applicable rule.
4. Assign status using exact definitions:
   - `met`: doses_received >= doses_required (after any reduction)
   - `partial`: doses_received > 0 and < doses_required
   - `missing`: doses_received == 0
   - `not_applicable`: requirement doesn't apply to this patient
   - `needs_review`: required data (date_of_birth, a dose_date) is missing
5. Verify the status against the definitions before finalizing.
6. Explain reasoning in `notes` whenever a conditional rule was applied.

Models are instructed not to guess missing dates, and to use
`needs_review` instead.

## Required output format
```json
{
  "patient_id": "user_001",
  "state": "California",
  "patient_grade_level": "8",
  "model_used": "<model name>",
  "overall_compliant": true,
  "per_disease": [
    {
      "disease": "Pertussis",
      "doses_required": 5,
      "doses_received": 4,
      "status": "met",
      "notes": "Dose 4 given at age 4y2m, satisfying the reduced 4-dose rule."
    }
  ]
}
```

## Models

### Gemini (`model_gemini.py`)
Called via Vertex AI's `GenerativeModel` interface. Uses the project's
existing Google Cloud credentials -- no separate API key required.
Status: implemented and tested against the benchmark dataset.

### Llama 4 (`model_llama4.py`)
Called via Vertex AI's Llama 4 API Service (a hosted, pay-per-token
endpoint -- no separate deployment step). Uses the same Google Cloud
credentials as Gemini -- no separate API key.

Two things worth knowing if this ever needs debugging again:
- The available model in this project is Llama 4 Maverick
  (`meta/llama-4-maverick-17b-128e-instruct-maas`), not Scout.
- The service runs in the `us-east5` region, not `us-central1` where the
  rest of this project's Vertex AI calls happen. Calling the wrong region
  produces a "model not found" error that looks like a permissions
  problem but isn't.

Requires the Llama Community License Agreement to be accepted once in
Vertex AI Model Garden for the project.
Status: implemented, pending a first test run.

### OpenAI (`model_openai.py`)
Called via the OpenAI API. Requires an `OPENAI_API_KEY` environment
variable, tied to an account with billing enabled.
Status: implemented, blocked on API key provisioning.

### Palmyra X4 (`model_palmyra.py`)
Called via Writer's direct API. Requires a `WRITER_API_KEY` environment
variable. Note: Palmyra X4 is scheduled for deprecation on November 18,
2026, with Palmyra X5 as the replacement; `MODEL_NAME` can be updated to
`"palmyra-x5"` if needed.
Status: implemented, blocked on API key provisioning.

### MedGemma (`model_medgemma.py`)
Requires deployment to a dedicated Vertex AI endpoint before use --
MedGemma is not available as a pay-per-call hosted service like the other
models. Deployment provisions GPU resources and bills for endpoint uptime
regardless of request volume. Deployment instructions are in the module
docstring.
Status: implemented, blocked on endpoint deployment.

### Form Parser
Form Parser is Google's document extraction/OCR service and does not fit
the compliance-comparison task the other five models perform. It is
suited to a different stage of the pipeline: extracting structured
dose-count data directly from state requirement PDFs (the task currently
done by manual extraction, as with `California.json`), rather than
reasoning about a ledger's compliance against a requirement set. It does
not have a corresponding `model_<name>.py` file for this reason -- any
future use of Form Parser belongs in the requirement-extraction step of
the pipeline, not the comparison step.

## Known Gaps

### No shared "today's date" reference across models
Requirements with grade-specific applicability (e.g., a 7th-grade-only
booster) are sometimes evaluated inconsistently, because no model is given
a fixed reference date to calculate the patient's current age or infer
their current grade level from date_of_birth alone.

Planned fix: add a `reference_date` parameter to every model's
`run_model_comparison()` function, passed identically into every prompt
(e.g., "Today's date is {reference_date}; use this to calculate current
age and infer grade level where needed"). Not yet implemented, to be
addressed once fixed consistently across all model files rather than
inside any single one.

### Patient grade_level is not tracked in patient data
Currently passed as a fixed placeholder string at call time. A real
Patient Profile (date_of_birth, institution_type, grade level) is
specified in the original design doc but not yet populated by the
pipeline.

### State requirement notes are free text
Every model parses conditional dose-reduction rules from free text at
inference time. A more reliable but higher-effort alternative would be
pre-structuring each conditional rule into a machine-readable format
ahead of time.

## Testing checklist for each model
1. Run against the benchmark dataset (113 synthetic patients) and
   California's requirements; compare output against the dose-count-only
   baseline and against other models' output for the same patients.
2. Test a dose given at an exact age boundary (e.g., age 4 exactly) to
   check boundary-condition handling.
3. Test a patient whose grade level should make a requirement
   `not_applicable`, and confirm it is correctly skipped rather than
   marked `missing`.
4. Check specifically for the missing-vs-partial pattern described above,
   since prompt wording differences between models could reintroduce it.