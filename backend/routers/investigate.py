import json
from fastapi import APIRouter, HTTPException
from core.config import RESULT_DIR
from schemas.investigate import InvestigateRequest
from services.ai_investigator import (
    ask_investigator,
    InvestigatorRateLimitError,
)

router = APIRouter(tags=["AI Investigation"])


@router.post("/investigate")
async def investigate(payload: InvestigateRequest):
    detections_path = RESULT_DIR / f"{payload.analysis_id}_detections.json"

    if not detections_path.exists():
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

    try:
        with open(detections_path, "r") as file:
            detections = json.load(file)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load detection data: {str(e)}"
        )

    try:
        answer = ask_investigator(
            detections,
            payload.question,
            [turn.model_dump() for turn in payload.history]
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
