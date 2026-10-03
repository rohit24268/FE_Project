import json
from fastapi import APIRouter, HTTPException
from core.config import RESULT_DIR
from core.database import get_db
from schemas.investigate import InvestigateRequest
from services.ai_investigator import (
    ask_investigator,
    InvestigatorRateLimitError,
)

router = APIRouter(tags=["AI Investigation"])


def _load_detections(analysis_id: str) -> list | None:
    """Load detections from MongoDB or JSON fallback. Returns None if not found."""
    db = get_db()

    if db is not None:
        try:
            detections = list(
                db["detection_results"]
                .find(
                    {"analysis_id": analysis_id},
                    {"_id": 0},
                )
                .sort("frame_number", 1)
            )
            if detections:
                return detections
        except Exception as e:
            print(f"[MongoDB] Error loading detections for investigation: {e}")

    # JSON fallback
    detections_path = RESULT_DIR / f"{analysis_id}_detections.json"
    if not detections_path.exists():
        return None

    try:
        with open(detections_path, "r") as file:
            return json.load(file)
    except Exception:
        return None


def _load_threat_data(analysis_id: str) -> dict | None:
    """Load threat analysis from MongoDB or JSON fallback."""
    db = get_db()

    if db is not None:
        try:
            result = db["investigation_reports"].find_one(
                {"analysis_id": analysis_id},
                {"_id": 0, "threat_summary": 1},
            )
            if result and result.get("threat_summary"):
                return result["threat_summary"]
        except Exception as e:
            print(f"[MongoDB] Error loading threat data for investigation: {e}")

    # JSON fallback
    threats_path = RESULT_DIR / f"{analysis_id}_threats.json"
    if threats_path.exists():
        try:
            with open(threats_path, "r") as t_file:
                return json.load(t_file)
        except Exception:
            pass

    return None


@router.post("/investigate")
async def investigate(payload: InvestigateRequest):
    detections = _load_detections(payload.analysis_id)

    if detections is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No detection data found for this analysis_id. "
                "Run /analyze-video first."
            )
        )

    if not payload.question or not payload.question.strip():
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty"
        )

    threat_data = _load_threat_data(payload.analysis_id)

    try:
        answer = ask_investigator(
            detections,
            payload.question,
            [turn.model_dump() for turn in payload.history],
            threat_analysis=threat_data
        )
    except InvestigatorRateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI investigation assistant failed: {str(e)}"
        )

    return {
        "success": True,
        "answer": answer
    }
