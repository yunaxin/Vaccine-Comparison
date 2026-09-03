# State Requirement Extraction Checklist

Use this before hand-extracting (or pointing a model at) any new state's
immunization requirement document. Takes 2-3 minutes per document and
saves you from repeating the Alabama/Arizona dead end -- both looked like
the right kind of document but turned out to be blank tracking certificates
with no actual dose-count numbers.

## Step 1: Does this document state actual dose-count numbers?

Look for language like "X doses required" or a table with a doses-required
column -- not just a list of vaccine names.

- ✅ PASS example: California CDPH 286 -- "5 doses meet TK/K-12 requirement,
  as do: 4 doses, if >=1 dose given at age >=4 years"
- ❌ FAIL example: Alabama Certificate of Immunization, Arizona ASIR109R --
  blank date-entry grids with vaccine names but no required-count numbers
  anywhere on the page

**If FAIL:** Stop. This document can't be extracted from as-is. Either:
  (a) find a different document from the same state (the agency's actual
      requirements chart, separate from the blank tracking form), or
  (b) flag it and move to the next state -- don't force-extract a document
      that has no numbers to give you.

## Step 2: What's the applicable population per requirement?

For each vaccine/disease line, does the document specify who it applies to?

- All students K-12? (most common -- maps to `grade_or_age_range: "K-12"`
  or similar)
- A specific grade only? (e.g., "7th grade Tdap booster" -- California had
  this as a *separate* line item from the base DTaP series)
- Pre-K / childcare only, not required K-12? (California's Hib requirement
  was this case -- easy to miss if you're skimming)
- Age-based rather than grade-based? (some states phrase requirements by
  age, not grade)

**Write down the exact applicable population as stated** -- don't
paraphrase or assume "probably all grades" if the document doesn't say so
explicitly.

## Step 3: Are there conditional / reduced-dose rules?

Does the document say something like "X doses required, OR Y doses
acceptable if [condition]"?

- Common patterns seen so far: "fewer doses OK if the last one was given
  after a certain age"
- **Do NOT try to pre-compute or simplify these into a fixed number.**
  Copy the exact rule language into the `notes` field, verbatim or close
  to it. The AI agent (per AI_AGENT_SPEC.md) is meant to evaluate these
  conditions against a specific patient's actual dose-ages at comparison
  time -- if you flatten the rule into "5 doses" during extraction, you've
  silently thrown away information the agent needs.

## Step 4: Build the JSON

Once a document passes Steps 1-3, use this shape (matches
`StateRequirementSet` in schema.py):

```json
{
  "state": "StateName",
  "source_agency": "Full agency name",
  "source_url": "Direct URL or document identifier",
  "requirements": [
    {
      "disease": "Disease name (match vaccine_mapping.json disease names where possible)",
      "doses_required": <base number of doses>,
      "grade_or_age_range": "Applicable population, as stated in the document",
      "notes": "Any conditional/reduced-dose language, copied close to verbatim"
    }
  ]
}
```

Save as `data/state_requirements/<StateName>.json`, matching the filename
of the source PDF already in that folder (e.g., `Texas.pdf` ->
`Texas.json`).

## Quick pass/fail log (fill in as you go)

| State | Step 1 (has numbers?) | Notes |
|---|---|---|
| California | ✅ Pass | CDPH 286 -- used as reference/first extraction |
| Alabama | ❌ Fail | Blank Certificate of Immunization, no dose counts stated |
| Arizona | ❌ Fail | ASIR109R blank tracking card, no dose counts stated |
| Texas | ⏸ Pending | Not yet checked against this checklist |
| New York | ⏸ Pending | Not yet checked against this checklist |

## When a state fails Step 1

Don't try to force it. Options, roughly in order of effort:
1. Search the state's Dept. of Health/Education site directly for a
   "school immunization requirements chart" or similar -- often a
   different document than whatever's linked on our own site
2. Flag to lead/team -- may indicate our own data source (VaccineGenie's
   "View Form" links) needs updating for that state
3. Move on to the next state and circle back later