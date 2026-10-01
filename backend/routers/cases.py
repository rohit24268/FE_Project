import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from core.config import RESULT_DIR
from core.database import get_db
from schemas.cases import CreateCaseRequest, LinkAnalysisRequest

router = APIRouter(tags=["Cases"])

CASES_FILE = RESULT_DIR / "cases.json"


# --------------------------------------------------
# JSON FALLBACK HELPERS (kept for backward compat)
# --------------------------------------------------

def _load_cases_json() -> list:
    if not CASES_FILE.exists():
        return []
    try:
        with open(CASES_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_cases_json(cases: list) -> None:
    with open(CASES_FILE, "w") as f:
        json.dump(cases, f, indent=2)


# --------------------------------------------------
# ENDPOINTS
# --------------------------------------------------

@router.get("/cases")
def list_cases():
    """Return all investigation cases."""
    db = get_db()

    if db is not None:
        try:
            cases = list(
                db["cases"]
                .find({}, {"_id": 0})
                .sort("created_at", -1)
            )
            return cases
        except Exception as e:
            print(f"[MongoDB] Error listing cases: {e}")

    # JSON fallback
    return _load_cases_json()


@router.post("/cases", status_code=201)
def create_case(payload: CreateCaseRequest):
    """Create a new investigation case."""
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="title cannot be empty")

    case = {
        "case_id": str(uuid.uuid4()),
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "investigator": payload.investigator.strip(),
        "status": payload.status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis_ids": [],
    }

    db = get_db()

    if db is not None:
        try:
            db["cases"].insert_one(case.copy())
        except Exception as e:
            print(f"[MongoDB] Error creating case: {e}")

    # Also save to JSON (temporary dual-write)
    cases = _load_cases_json()
    cases.insert(0, case)
    _save_cases_json(cases)

    return case


@router.get("/cases/{case_id}")
def get_case(case_id: str):
    """Get a single case by ID."""
    db = get_db()

    if db is not None:
        try:
            case = db["cases"].find_one(
                {"case_id": case_id},
                {"_id": 0},
            )
            if case:
                return case
        except Exception as e:
            print(f"[MongoDB] Error getting case: {e}")

    # JSON fallback
    for case in _load_cases_json():
        if case["case_id"] == case_id:
            return case

    raise HTTPException(status_code=404, detail="Case not found")


@router.post("/cases/{case_id}/link-analysis")
def link_analysis_to_case(case_id: str, payload: LinkAnalysisRequest):
    """Link an analysis ID to a case."""
    db = get_db()

    if db is not None:
        try:
            result = db["cases"].find_one_and_update(
                {"case_id": case_id},
                {"$addToSet": {"analysis_ids": payload.analysis_id}},
                return_document=True,
                projection={"_id": 0},
            )
            if result:
                # Dual-write to JSON
                cases = _load_cases_json()
                for c in cases:
                    if c["case_id"] == case_id:
                        if payload.analysis_id not in c["analysis_ids"]:
                            c["analysis_ids"].append(payload.analysis_id)
                        break
                _save_cases_json(cases)
                return result
        except Exception as e:
            print(f"[MongoDB] Error linking analysis: {e}")

    # JSON fallback
    cases = _load_cases_json()
    for case in cases:
        if case["case_id"] == case_id:
            if payload.analysis_id not in case["analysis_ids"]:
                case["analysis_ids"].append(payload.analysis_id)
            _save_cases_json(cases)
            return case

    raise HTTPException(status_code=404, detail="Case not found")


@router.patch("/cases/{case_id}/status")
def update_case_status(case_id: str, status: str):
    """Update the status of a case (open / pending / closed)."""
    allowed = {"open", "pending", "closed"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")

    db = get_db()

    if db is not None:
        try:
            result = db["cases"].find_one_and_update(
                {"case_id": case_id},
                {"$set": {"status": status}},
                return_document=True,
                projection={"_id": 0},
            )
            if result:
                # Dual-write to JSON
                cases = _load_cases_json()
                for c in cases:
                    if c["case_id"] == case_id:
                        c["status"] = status
                        break
                _save_cases_json(cases)
                return result
        except Exception as e:
            print(f"[MongoDB] Error updating status: {e}")

    # JSON fallback
    cases = _load_cases_json()
    for case in cases:
        if case["case_id"] == case_id:
            case["status"] = status
            _save_cases_json(cases)
            return case

    raise HTTPException(status_code=404, detail="Case not found")
