# AI Agent Spec: Ledger-to-State-Requirement Compliance Comparison

## Purpose
Given one patient's immunization ledger and one state's structured immunization
requirements, determine the patient's compliance status per disease --
including cases the current stub logic (`compare.py`) cannot handle:
age-conditional dose reductions, grade-specific booster rules, and
requirements that don't apply to the patient's grade/age at all.

## Why this needs a model, not just more Python
The stub in `compare.py` only compares raw dose counts. Real state
requirements have conditional logic in free text, e.g.:
  "5 doses meet requirement, OR 4 if >=1 dose given at age >=4 years,
   OR 3 if >=1 Tdap dose given at age >=7 years"
Evaluating this requires reading the patient's dose-by-dose ages against the
rule's text -- exactly the kind of reasoning-over-unstructured-text task a
model is suited for and hardcoded Python isn't (without turning the rules
into a rigid, brittle rule-engine that breaks the moment a new state phrases
things differently).

## Inputs the agent will receive

**1. Patient ledger** (matches `PatientLedger` in schema.py):
```json
{
  "user_id": "user_001",
  "patient_name": "...",
  "date_of_birth": "YYYY-MM-DD",   // NOTE: not yet in ledger output -- needs
                                     // to be added once Patient Profile data
                                     // exists (see design doc open question)
  "ledger": [
    {
      "disease_name": "Pertussis",
      "doses_received": [
        {"dose_label": "Dose 1", "vaccine_name": "DTaP", "dose_date": "2018-02-28"},
        ...
      ],
      "doses_completed_count": 4,
      ...
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

**3. Patient's grade/age context** (needed to evaluate grade-specific and
age-conditional rules -- currently a placeholder in the pipeline, see
"Known Gaps" below):
```json
{"grade_level": "8", "date_of_birth": "2011-03-15"}
```

## The task, stated plainly for the model

> You are checking whether a patient's vaccination record satisfies a
> state's school immunization requirements.
>
> For each requirement in the state's requirement list:
> 1. Check if the requirement applies to this patient given their grade
>    level (see `grade_or_age_range`). If not, mark it `not_applicable`
>    and do not evaluate it further.
> 2. If it applies, calculate the patient's age at the date of each
>    relevant dose (using `date_of_birth` and each `dose_date`).
> 3. Read the `notes` field carefully -- it may describe alternate,
>    reduced dose counts that are acceptable if specific doses were
>    given at or after a specific age (e.g., "3 doses OK if 1 given
>    at age >=4"). Apply whichever rule the patient's actual dose ages
>    satisfy, using the MOST FAVORABLE rule that legitimately applies.
> 4. Assign a status: "met", "partial", "missing", or "not_applicable".
> 5. Explain your reasoning in `notes` for any case where you applied a
>    conditional/reduced-dose rule rather than just the base dose count
>    -- so a human reviewer can verify your reasoning, not just your
>    conclusion.
>
> Do not guess or infer missing dates. If `date_of_birth` or a
> `dose_date` is missing and it's required to evaluate a conditional
> rule, mark that disease's status as "needs_review" rather than
> guessing.

## Required output format
Must exactly match `ComparisonResult` in schema.py:
```json
{
  "patient_id": "user_001",
  "state": "California",
  "patient_grade_level": "8",
  "model_used": "<model name here>",
  "overall_compliant": true,
  "per_disease": [
    {
      "disease": "Pertussis",
      "doses_required": 5,
      "doses_received": 4,
      "status": "met",
      "notes": "Patient has 4 doses of DTaP, with dose 4 given at age 4y2m (>=4 years) -- satisfies the reduced 4-dose rule per state notes."
    }
  ]
}
```

## Known gaps this spec depends on (flag to lead, not yours to solve alone)
1. **Patient date_of_birth is not currently in ledger output.** The Patient
   Profile schema in the original design doc specifies this field but it's
   never populated by the current pipeline. The agent cannot evaluate any
   age-conditional rule without it.
2. **Patient grade_level is not tracked anywhere yet.** Currently hardcoded
   as `"K-12"` in `compare.py` as a placeholder -- needs a real source.
3. **State requirement notes are free text, not structured rules.** This
   spec assumes the model parses the notes text at inference time. An
   alternative (more reliable, more work) would be pre-structuring each
   conditional rule into its own machine-readable format ahead of time --
   worth discussing with the team once we see how well models 1-shot the
   free-text version.

## What to test once model access is available
1. Run this spec against California + the one test patient (Patrick Weber)
   -- compare the model's output to the stub's dose-count-only output, and
   manually verify which one is actually correct.
2. Deliberately test an edge case: a patient with a dose given exactly at
   the age-4 boundary, to see if the model handles boundary conditions
   correctly.
3. Test a patient whose grade level should make a requirement
   `not_applicable` (e.g., a Pre-K-only requirement checked against a
   10th grader) -- confirm the model correctly skips it rather than
   incorrectly flagging it as missing.