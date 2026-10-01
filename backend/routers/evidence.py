import json

from fastapi import APIRouter, HTTPException
from core.config import RESULT_DIR
from core.database import get_db

router = APIRouter(tags=["Evidence"])


def _build_description(detection: dict) -> str:
    obj = detection.get("object", "Unknown")
    conf = float(detection.get("confidence", 0))
    ts = float(detection.get("timestamp", 0))
    track_id = detection.get("track_id")
    threat_cat = detection.get("threat_category", "NONE")

    desc = (
        f"{obj.capitalize()} detected at {ts:.2f}s "
        f"with {conf * 100:.1f}% confidence"
    )
    if track_id is not None:
        desc += f" (Track #{track_id})"
    if threat_cat and threat_cat != "NONE":
        desc += f" — {threat_cat.replace('_', ' ').title()}"
    return desc


def _detection_to_evidence(analysis_id: str, d: dict) -> dict:
    """Convert a detection record into an evidence item."""
    is_threat = d.get("is_threat", False)
    return {
        "analysis_id": analysis_id,
        "frame": d.get("frame"),
        "timestamp": d.get("timestamp"),
        "object": d.get("object"),
        "confidence": d.get("confidence"),
        "track_id": d.get("track_id"),
        "is_threat": is_threat,
        "threat_category": d.get("threat_category", "NONE"),
        "attributes": d.get("attributes", ""),
        "bounding_box": d.get("bounding_box"),
        "evidence_type": "THREAT" if is_threat else "DETECTION",
        "description": _build_description(d),
    }


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
            print(f"[MongoDB] Error loading threat data: {e}")

    # JSON fallback
    threats_path = RESULT_DIR / f"{analysis_id}_threats.json"
    if threats_path.exists():
        try:
            with open(threats_path, "r") as f:
                return json.load(f)
        except Exception:
            pass

    return None


@router.get("/evidence/{analysis_id}")
def get_evidence(analysis_id: str):
    """
    Return evidence items derived from detection results.
    Reads from MongoDB first, falls back to JSON files.
    """
    evidence_items = []

    # Try MongoDB first
    db = get_db()
    if db is not None:
        try:
            detections = list(
                db["evidence"]
                .find(
                    {"analysis_id": analysis_id},
                    {"_id": 0},
                )
                .sort("frame", 1)
            )
            if detections:
                evidence_items = [
                    _detection_to_evidence(analysis_id, d)
                    for d in detections
                ]
        except Exception as e:
            print(f"[MongoDB] Error loading evidence: {e}")

    # JSON fallback if MongoDB had no data
    if not evidence_items:
        detections_path = RESULT_DIR / f"{analysis_id}_detections.json"

        if not detections_path.exists():
            raise HTTPException(
                status_code=404,
                detail=(
                    "No detection data found for this analysis_id. "
                    "Run /analyze-video first."
                ),
            )

        with open(detections_path, "r") as f:
            detections = json.load(f)

        evidence_items = [
            _detection_to_evidence(analysis_id, d)
            for d in detections
        ]

    threat_data = _load_threat_data(analysis_id)

    return {
        "analysis_id": analysis_id,
        "total_evidence": len(evidence_items),
        "threat_analysis": threat_data,
        "evidence": evidence_items,
    }
