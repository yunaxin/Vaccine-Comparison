# Results: Model Comparison and Agent Testing

## What was tested

Two different approaches to the same question -- does a patient's
immunization record satisfy a state's school entry requirements:

1. **Direct model comparison** -- California, using Gemini and Llama 4,
   scored against a verified ground truth
2. **Agentic, tool-based approach** -- Washington, using an ADK agent
   with function-calling tools, tested on one real patient

## Part 1: Model comparison results (California)

### Method
Gemini and Llama 4 were each given the same 50 real patients (from the
Synthea benchmark dataset) and California's requirements, and asked to
determine compliance per disease directly, including any age/interval
reasoning.

To score their answers, a verified ground truth was built separately
using deterministic date-math logic (`dose_validity_tool.py`) -- not
another model's opinion, but calculated compliance based on each
patient's actual dose dates against California's documented rules.

One requirement was excluded from scoring: the 7th-12th grade Pertussis
Tdap booster, since checking it correctly requires knowing a patient's
actual school grade, which this project's data does not include.

### Results

| Model | Checks scored | Correct | Accuracy |
|---|---|---|---|
| Gemini | 500 | 497 | **99.4%** |
| Llama 4 | 500 | 495 | **99.0%** |

### Per-class metrics

**Gemini:**
| Status | Precision | Recall | F1 |
|---|---|---|---|
| met | 100.0% | 100.0% | 100.0% |
| missing | 100.0% | 99.0% | 99.5% |
| not_applicable | 100.0% | 100.0% | 100.0% |
| partial | 97.5% | 100.0% | 98.7% |

**Llama 4:**
| Status | Precision | Recall | F1 |
|---|---|---|---|
| met | 97.3% | 90.0% | 93.5% |
| missing | 100.0% | 100.0% | 100.0% |
| not_applicable | 100.0% | 100.0% | 100.0% |
| partial | 96.7% | 99.2% | 97.9% |

### What the remaining errors look like
- Gemini's 3 errors were all the same pattern: marking Pertussis
  "partial" when the correct answer was "missing"
- Llama 4's 5 errors included 4 tied to a single patient, where it
  marked several diseases "partial" instead of "met" -- likely a
  mishandled reduction-exception check for that specific case, not
  scattered random error

Both models perform very well on this task. Gemini was slightly more
accurate and had more consistent per-class performance; Llama 4's
errors were more concentrated in dose-reduction exception handling.


## Part 2: Agent test results (Washington)

### Method
Unlike the direct-comparison approach, the Washington agent does not
reason about dates itself. It calls two tools: one to look up a
patient's real dose history by name, and one that performs all date and
interval math deterministically (the same logic used to build the
California ground truth above). The agent's job is to call these tools,
apply the state's documented exceptions, and produce a final structured
result.

### Result
Tested on one real patient (Reynaldo722 Beatty507, a well-vaccinated
child with a complete dose history). The agent:
- Correctly called both tools for all 9 applicable diseases
- Correctly identified that no dose-reduction exceptions changed the
  outcome for this patient (all base dose counts were met as given)
- Produced a fully accurate result across all 9 diseases, matching
  independently-verified ground truth exactly
- Output a clean, structured JSON summary suitable for programmatic
  scoring, in addition to its plain-language explanation

This is a single verified test case, not a scaled accuracy measurement
like the California model comparison above.