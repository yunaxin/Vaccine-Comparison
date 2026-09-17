# AI Agent Spec: Ledger-to-State-Requirement Compliance Comparison

This project has two different approaches to the same underlying
question -- does a patient's immunization record satisfy a state's
school entry requirements -- built at different points in the project.
Both are documented here since both are still relevant.

## Approach 1: Direct model comparison (California)

The first approach sends a state's full requirement text and a
patient's ledger directly to a model in one prompt, and asks the model
to reason through compliance itself, including any date/age math.

### The problem with dose counting alone
Real state requirements have conditional logic written into free text,
e.g.: "5 doses meet requirement, OR 4 if at least one dose given at age
4 or older, OR 3 if at least one Tdap dose given at age 7 or older." A
fixed dose-count comparison can't apply a rule like this correctly on
its own, which is why this approach hands the reasoning to a model.

### Models tested (California)
- **Gemini** (`model_gemini.py`) -- working, tested against the
  benchmark dataset, 50-patient run completed
- **Llama 4** (`model_llama4.py`) -- working, 50-patient run completed.
  Uses Vertex AI's Llama 4 API Service (Maverick variant, `us-east5`
  region -- both had to be corrected from initial guesses)
- **Claude** (`model_claude.py`) -- blocked; requires a formal business
  access request submitted to and approved by Anthropic, not a simple
  enable
- **Mistral** (`model_mistral.py`) -- blocked on missing Google Cloud
  IAM permissions to enable the model
- **OpenAI, Palmyra** -- out of current scope once the task narrowed to
  GCP-hosted models only

### Known limitation of this approach
The model does its own date arithmetic, which was inconsistent across
runs in early testing (a missing-vs-partial status bug, and
inconsistent handling of age-boundary conditions). This is the
motivation for Approach 2.

## Approach 2: Agentic, tool-based (Washington)

The second approach separates the two jobs: a deterministic Python tool
does all date/age/interval math reliably, and an AI agent (built with
Google's Agent Development Kit) orchestrates calling that tool and
explains the results in plain language. This is a more reliable design
than asking a model to do date arithmetic in its own reasoning.

### Components
- **`data/state_requirements/Washington.json`** -- Washington's
  requirements, verified against two independent DOH sources
  (DOH-348-284 for detailed per-dose age/interval data, DOH-348-295 for
  the summary chart). Includes structured numeric fields
  (`minimum_age_days`, `minimum_interval_days`) alongside human-readable
  text, plus `reduction` rules for dose-count exceptions.
- **`src/dose_validity_tool.py`** -- the deterministic logic. Given a
  dose date, date of birth, and the schedule rules, it answers "is this
  dose valid?" or "when does this dose become eligible?" with no AI
  involved. Also contains `evaluate_disease_compliance()`, the single
  shared entry point that applies dose-reduction exceptions and
  computes an overall status -- used identically by the agent and by
  the Streamlit app, so there is one correct implementation rather than
  logic duplicated across interfaces.
- **`adk_agents/washington_agent/`** -- the ADK agent itself. Has two
  tools: `lookup_patient_ledger` (finds a patient's data by name from
  the benchmark dataset) and `check_disease_compliance` (calls the
  dose validity logic). The agent's job is to call these tools, apply
  the state's dose-reduction notes where the tool alone doesn't decide
  applicability, and explain the result clearly.
- **`app.py`** -- a Streamlit reference app. Imports
  `dose_validity_tool.py` directly and computes compliance for any
  patient in the benchmark dataset. This is NOT an AI agent -- it makes
  no model calls and costs nothing to run. It exists as a fast, free way
  to browse the same underlying logic the agent's tool uses,
  independent of Gemini access or quota.

### Verified test cases (Washington agent)
- An overdue teenage patient with zero doses -- correctly reported as
  missing, not falsely marked eligible
- A newborn -- correctly reported as not-yet-eligible with a future
  date, not missing
- A hand-constructed fully compliant patient -- correctly applied the
  Polio dose-reduction exception and reported "met"
- A real adult patient from the benchmark dataset, checked against K-12
  rules -- correctly computed per the rules as written (see Known Gaps:
  this exposed the missing age/grade applicability filter, not an agent
  error)
- A real school-age patient (Reynaldo722 Beatty507) with a complete,
  well-timed dose history -- correctly reported "met" across all 9
  diseases, with correct reasoning about which reduction exceptions did
  and didn't apply

### A real bug found and fixed
`check_next_dose_eligibility()` originally didn't receive Hepatitis B's
compound constraint (dose 3 needing both >=8 weeks after dose 2 AND
>=16 weeks after dose 1) when calculating eligibility for a dose not
yet given -- it only applied that constraint when validating an
already-given dose. Fixed by passing the constraint and all patient
doses into the eligibility function and taking the latest of all
candidate dates.

## Known Gaps

### No patient grade/age applicability filter
Neither approach currently checks whether a patient's age even falls
within the grade range a requirement applies to before running the
compliance check. This surfaced clearly when an adult patient was
checked against Washington's K-12 rules -- the agent applied the rules
correctly as written, but the question itself wasn't meaningful for
that patient. A real Patient Profile (date of birth plus grade level,
as specified in the original design doc) is needed to filter this
properly.

### No shared "today's date" reference in Approach 1's models
Requirements tied to a specific grade (e.g. a 7th-grade-only booster)
were sometimes evaluated inconsistently across models, since no model
was given a fixed reference date to calculate current age or grade
from. Not an issue in Approach 2, since the tool always computes
against an explicit `today` value.

### State requirement notes are still free text in Approach 1
Every model in the direct-comparison approach still has to read and
interpret conditional rules from prose at inference time. Approach 2
solves this for Washington by encoding the rules as structured data
(`dose_schedule`, `reduction`) -- worth doing the same for any other
state that gets the agentic treatment.

### Only Washington has the agentic treatment so far
California was tested with Approach 1 only. Extending Approach 2 (real
dose-schedule data, the shared tool, an ADK agent) to additional states
is the natural next step if that's the expected scope.