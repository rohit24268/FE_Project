import json

from fastapi import APIRouter, HTTPException
from core.config import RESULT_DIR

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


@router.get("/evidence/{analysis_id}")
def get_evidence(analysis_id: str):
    """
    Return evidence items derived from existing YOLO detection results.
    Each detection becomes an evidence item with type, description, and threat metadata.
    """
    detections_path = RESULT_DIR / f"{analysis_id}_detections.json"
    threats_path = RESULT_DIR / f"{analysis_id}_threats.json"

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

    threat_data = None
    if threats_path.exists():
        try:
            with open(threats_path, "r") as f:
                threat_data = json.load(f)
        except Exception:
            threat_data = None

    evidence_items = []
    for d in detections:
        is_threat = d.get("is_threat", False)
        evidence_items.append(
            {
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
        )

    return {
        "analysis_id": analysis_id,
        "total_evidence": len(evidence_items),
        "threat_analysis": threat_data,
        "evidence": evidence_items,
    }
