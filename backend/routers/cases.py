import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from core.config import RESULT_DIR
from schemas.cases import CreateCaseRequest, LinkAnalysisRequest

router = APIRouter(tags=["Cases"])

CASES_FILE = RESULT_DIR / "cases.json"


def _load_cases() -> list:
    if not CASES_FILE.exists():
        return []
    try:
        with open(CASES_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_cases(cases: list) -> None:
    with open(CASES_FILE, "w") as f:
        json.dump(cases, f, indent=2)


@router.get("/cases")
def list_cases():
    """Return all investigation cases."""
    return _load_cases()


@router.post("/cases", status_code=201)
def create_case(payload: CreateCaseRequest):
    """Create a new investigation case."""
    if not payload.case_name.strip():
        raise HTTPException(status_code=400, detail="case_name cannot be empty")

    cases = _load_cases()
    case = {
        "case_id": str(uuid.uuid4()),
        "case_name": payload.case_name.strip(),
        "description": payload.description.strip(),
        "investigator": payload.investigator.strip(),
        "status": payload.status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis_ids": [],
    }
    cases.insert(0, case)
    _save_cases(cases)
    return case


@router.get("/cases/{case_id}")
def get_case(case_id: str):
    """Get a single case by ID."""
    for case in _load_cases():
        if case["case_id"] == case_id:
            return case
    raise HTTPException(status_code=404, detail="Case not found")


@router.post("/cases/{case_id}/link-analysis")
def link_analysis_to_case(case_id: str, payload: LinkAnalysisRequest):
    """Link an analysis ID to a case."""
    cases = _load_cases()
    for case in cases:
        if case["case_id"] == case_id:
            if payload.analysis_id not in case["analysis_ids"]:
                case["analysis_ids"].append(payload.analysis_id)
            _save_cases(cases)
            return case
    raise HTTPException(status_code=404, detail="Case not found")


@router.patch("/cases/{case_id}/status")
def update_case_status(case_id: str, status: str):
    """Update the status of a case (open / pending / closed)."""
    allowed = {"open", "pending", "closed"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")
    cases = _load_cases()
    for case in cases:
        if case["case_id"] == case_id:
            case["status"] = status
            _save_cases(cases)
            return case
    raise HTTPException(status_code=404, detail="Case not found")
