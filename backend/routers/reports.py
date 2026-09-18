import json

from fastapi import APIRouter, HTTPException
from core.config import RESULT_DIR

router = APIRouter(tags=["Reports"])


def _build_findings(
    detections: list,
    threat_data: dict | None,
    object_counts: dict,
) -> list:
    findings = []

    if threat_data:
        level = threat_data.get("overall_threat_level", "SAFE")
        score = threat_data.get("max_threat_score", 0.0)
        incidents = threat_data.get("total_incidents", 0)
        findings.append(
            {
                "type": "threat_assessment",
                "title": f"Overall Threat Level: {level}",
                "detail": (
                    f"Peak threat risk score of {score * 100:.1f}% with "
                    f"{incidents} incident(s) detected."
                ),
            }
        )

        threat_summary = threat_data.get("threat_summary", {})
        seen_objs = threat_summary.get("threat_objects_seen", {})
        if seen_objs:
            obj_list = ", ".join(
                f"{obj} ({cnt}×)" for obj, cnt in seen_objs.items()
            )
            findings.append(
                {
                    "type": "threat_objects",
                    "title": "Threat-Class Objects Observed",
                    "detail": f"Objects flagged as threats: {obj_list}.",
                }
            )

    for obj, count in sorted(object_counts.items(), key=lambda x: -x[1]):
        findings.append(
            {
                "type": "object_summary",
                "title": f"{obj.capitalize()} — {count} Detection Event(s)",
                "detail": (
                    f"Object class '{obj}' was recorded "
                    f"{count} time(s) across the analysed footage."
                ),
            }
        )

    return findings


@router.get("/reports/{analysis_id}")
def get_report(analysis_id: str):
    """
    Generate a structured forensic report from existing detection and threat data.
    Includes case summary, threat assessment, chronological timeline, and key findings.
    """
    detections_path = RESULT_DIR / f"{analysis_id}_detections.json"
    threats_path = RESULT_DIR / f"{analysis_id}_threats.json"

    if not detections_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No analysis data found. Run /analyze-video first.",
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

    # Build object counts from detections
    object_counts: dict = {}
    for d in detections:
        obj = d.get("object", "unknown")
        object_counts[obj] = object_counts.get(obj, 0) + 1

    # Timeline: unique first-appearance per track + object
    seen: set = set()
    timeline = []
    for d in detections:
        track_id = d.get("track_id")
        obj = d.get("object", "Unknown")
        key = f"{track_id}_{obj}"
        if key not in seen:
            seen.add(key)
            timeline.append(
                {
                    "timestamp": d.get("timestamp"),
                    "frame": d.get("frame"),
                    "event": f"{obj.capitalize()} first appeared",
                    "object": obj,
                    "track_id": track_id,
                    "confidence": d.get("confidence"),
                    "is_threat": d.get("is_threat", False),
                    "threat_category": d.get("threat_category", "NONE"),
                    "attributes": d.get("attributes", ""),
                }
            )

    timeline.sort(key=lambda x: x["timestamp"] or 0)

    return {
        "analysis_id": analysis_id,
        "total_detections": len(detections),
        "object_counts": object_counts,
        "threat_analysis": threat_data,
        "timeline": timeline,
        "findings": _build_findings(detections, threat_data, object_counts),
    }
