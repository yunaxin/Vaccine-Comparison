# Vaccine Comparison

Checks whether a patient's immunization record satisfies a state's
school entry requirements, using a benchmark dataset of synthetic
patients and two different approaches: direct model comparison and an
agentic, tool-based design. See `AI_AGENT_SPEC.md` for full detail on
both approaches, what's been tested, and known gaps.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt   # or see individual install commands below
```

You'll also need:
- Google Cloud credentials for the project (`gcloud auth application-default login`)
- For the ADK agent specifically: `pip install google-adk`
- For the direct-comparison Claude model: `pip install "anthropic[vertex]"`
- For the Streamlit app: `pip install streamlit`

## What's in this repo

### Data pipeline
- `src/transform.py` -- cleans raw dose records (dates, missing fields, vaccine name normalization)
- `src/validate_extraction.py` -- checks cleaned records against the `RawDoseRecord` schema
- `src/build_ledger.py` -- groups a patient's doses by disease into a ledger, using `data/vaccine_mapping.json`
- `src/synthea_vaccine_map.py` -- translates Synthea's full vaccine descriptions into the short names `vaccine_mapping.json` uses
- `data/synthea_ledgers.json` -- the 113-patient benchmark dataset, already built into ledger form with real birthdates

### State requirements
- `data/state_requirements/California.json` -- hand-verified against the real CDPH 286 form
- `data/state_requirements/Washington.json` -- verified against two real DOH sources, includes structured per-dose age/interval data for the agentic approach

### Approach 1: direct model comparison (California)
- `src/models/model_gemini.py`, `model_llama4.py`, `model_claude.py`, `model_mistral.py` -- one file per model, same shared prompt/instructions, same input/output shape, so results are directly comparable
- `src/compare.py` -- the original no-AI dose-count-only baseline, for comparison against the models

To run one:
```python
from src.models.model_gemini import run_model_comparison
run_model_comparison(
    ledger_path="data/synthea_ledgers.json",
    requirement_path="data/state_requirements/California.json",
    output_path="data/comparisons/BENCHMARK_gemini_california_50.json",
    patient_grade_level="K-12",
    limit=50,
)
```

### Approach 2: agentic, tool-based (Washington)
- `src/dose_validity_tool.py` -- the deterministic date/age/interval logic and the shared `evaluate_disease_compliance()` entry point
- `adk_agents/washington_agent/` -- the ADK agent (Gemini + tool-calling). Has its own copies of `dose_validity_tool.py`, `Washington.json`, and `synthea_ledgers.json`, since ADK loads each agent's folder in isolation -- **if you fix a bug in the top-level `src/dose_validity_tool.py`, copy the fix into this folder too, or the agent will keep using the old version.**

To run the agent:
```bash
adk web adk_agents
```
Then open the dev UI in your browser, select `washington_agent`, and try something like:
> Check Reynaldo722 Beatty507's compliance with Washington's school immunization requirements.

### Streamlit reference app
`app.py` -- a free, no-AI lookup tool. Imports `dose_validity_tool.py` directly, so it's guaranteed to match the agent's underlying logic without needing a model call.

```bash
streamlit run app.py
```

## Known gaps (see `AI_AGENT_SPEC.md` for detail)
- No patient grade/age applicability filter yet -- checking an adult against K-12 rules produces technically-correct-but-meaningless results
- Only Washington has the agentic (Approach 2) treatment; other states would need the same structured `dose_schedule` and `reduction` data added to get the same benefits

## Git workflow notes
- `adk_agents/washington_agent/` intentionally duplicates a few files from `src/` and `data/` -- keep them in sync manually when either changes
- `.adk/` (ADK's local session database) is gitignored -- don't commit it
- Push benchmark result files (`data/comparisons/BENCHMARK_*.json`) as soon as a run finishes, since Colab/local sessions can be lost before they're saved
