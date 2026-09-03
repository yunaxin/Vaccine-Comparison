"""
schema.py

Data models for the ledger <-> state requirement comparison pipeline.
Written for Python 3.9 compatibility (Optional instead of X | None).
"""

from datetime import date
from typing import Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Input: a patient's ledger (reused shape from the transformation pipeline)
# ---------------------------------------------------------------------------
class LedgerDose(BaseModel):
    dose_label: str
    vaccine_name: str
    dose_date: date

class LedgerDisease(BaseModel):
    disease_name: str
    doses_received: list[LedgerDose]
    doses_completed_count: int
    doses_expected_count: Optional[int] = None
    completion_status: str
    missing_doses: list[str]

class PatientLedger(BaseModel):
    user_id: str
    patient_name: str
    ledger: list[LedgerDisease]


# ---------------------------------------------------------------------------
# Input: a state's structured requirements (extracted from the PDF)
# ---------------------------------------------------------------------------
class StateRequirement(BaseModel):
    disease: str
    doses_required: int
    grade_or_age_range: str
    notes: Optional[str] = None

class StateRequirementSet(BaseModel):
    state: str
    source_agency: str
    source_url: Optional[str] = None
    requirements: list[StateRequirement]


# ---------------------------------------------------------------------------
# Output: the comparison result — was this ledger produced by which model
# ---------------------------------------------------------------------------
class DiseaseComparisonResult(BaseModel):
    disease: str
    doses_required: int
    doses_received: int
    status: str  # "met", "partial", "missing"
    notes: Optional[str] = None

class ComparisonResult(BaseModel):
    patient_id: str
    state: str
    model_used: str
    overall_compliant: bool
    per_disease: list[DiseaseComparisonResult]