"""
Threat Scoring and Fusion Engine for CCTV Security Analysis.
Inspired by multi-model fusion pipelines (e.g. CCTV-Threat-Detection).

Evaluates:
1. Spatial detection: Lethal and blunt weapons, suspicious objects.
2. Spatial context & proximity: Proximity between weapons and persons (holding/brandishing).
3. Temporal aggregation: Persistent multi-frame incidents vs isolated false alarms.
"""

from typing import List, Dict, Any, Tuple
import math

# ---------------------------------------------------------------------------
# THREAT TAXONOMY & RISK WEIGHTS
# ---------------------------------------------------------------------------

# Lethal weapons: highest base risk
LETHAL_WEAPONS = {
    "gun": 0.85,
    "pistol": 0.85,
    "handgun": 0.85,
    "rifle": 0.90,
    "firearm": 0.90,
    "knife": 0.75,
    "dagger": 0.75,
    "sword": 0.80,
    "weapon": 0.80,
}

# Blunt / improvised weapons: medium-high base risk
BLUNT_WEAPONS = {
    "baseball bat": 0.55,
    "bat": 0.55,
    "crowbar": 0.60,
    "hammer": 0.50,
    "scissors": 0.45,
    "axe": 0.70,
}

# Suspicious / unattended items
SUSPICIOUS_ITEMS = {
    "backpack": 0.25,
    "suitcase": 0.25,
    "handbag": 0.20,
}

PERSON_CLASS = "person"


def normalize_class_name(name: str) -> str:
    """Normalizes object class string for matching."""
    return name.strip().lower().replace("-", " ").replace("_", " ")


def get_base_threat_weight(object_name: str) -> Tuple[float, str]:
    """
    Returns (base_weight, category) for a given object class name.
    Category is one of: 'LETHAL_WEAPON', 'BLUNT_WEAPON', 'SUSPICIOUS_ITEM', 'NONE'.
    """
    norm = normalize_class_name(object_name)

    if norm in LETHAL_WEAPONS:
        return LETHAL_WEAPONS[norm], "LETHAL_WEAPON"

    for k, weight in LETHAL_WEAPONS.items():
        if k in norm:
            return weight, "LETHAL_WEAPON"

    if norm in BLUNT_WEAPONS:
        return BLUNT_WEAPONS[norm], "BLUNT_WEAPON"

    for k, weight in BLUNT_WEAPONS.items():
        if k in norm:
            return weight, "BLUNT_WEAPON"

    if norm in SUSPICIOUS_ITEMS:
        return SUSPICIOUS_ITEMS[norm], "SUSPICIOUS_ITEM"

    return 0.0, "NONE"


def calculate_iou(b1: Dict[str, int], b2: Dict[str, int]) -> float:
    """Calculates Intersection-over-Union between two bounding boxes."""
    x1 = max(b1["x1"], b2["x1"])
    y1 = max(b1["y1"], b2["y1"])
    x2 = min(b1["x2"], b2["x2"])
    y2 = min(b1["y2"], b2["y2"])

    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    if intersection == 0:
        return 0.0

    area1 = (b1["x2"] - b1["x1"]) * (b1["y2"] - b1["y1"])
    area2 = (b2["x2"] - b2["x1"]) * (b2["y2"] - b2["y1"])
    union = area1 + area2 - intersection
    return intersection / union if union > 0 else 0.0


def calculate_center_distance(b1: Dict[str, int], b2: Dict[str, int]) -> float:
    """Calculates Euclidean distance between centers of two bounding boxes."""
    c1_x = (b1["x1"] + b1["x2"]) / 2.0
    c1_y = (b1["y1"] + b1["y2"]) / 2.0
    c2_x = (b2["x1"] + b2["x2"]) / 2.0
    c2_y = (b2["y1"] + b2["y2"]) / 2.0
    return math.hypot(c1_x - c2_x, c1_y - c2_y)


def is_in_proximity(box_weapon: Dict[str, int], box_person: Dict[str, int]) -> bool:
    """
    Checks whether a weapon is inside or immediately adjacent to a person's bounding box
    (indicating brandishing, carrying, or holding).
    """
    # 1. Bounding box intersection check
    x1 = max(box_weapon["x1"], box_person["x1"])
    y1 = max(box_weapon["y1"], box_person["y1"])
    x2 = min(box_weapon["x2"], box_person["x2"])
    y2 = min(box_weapon["y2"], box_person["y2"])

    if x2 > x1 and y2 > y1:
        # Weapon intersects person box
        return True

    # 2. Proximity check relative to person's dimensions (within 20% margin)
    person_w = box_person["x2"] - box_person["x1"]
    person_h = box_person["y2"] - box_person["y1"]
    margin = max(person_w, person_h) * 0.20

    expanded_person = {
        "x1": box_person["x1"] - margin,
        "y1": box_person["y1"] - margin,
        "x2": box_person["x2"] + margin,
        "y2": box_person["y2"] + margin,
    }

    ex1 = max(box_weapon["x1"], expanded_person["x1"])
    ey1 = max(box_weapon["y1"], expanded_person["y1"])
    ex2 = min(box_weapon["x2"], expanded_person["x2"])
    ey2 = min(box_weapon["y2"], expanded_person["y2"])

    return ex2 > ex1 and ey2 > ey1


def score_frame_threat(frame_detections: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Scores threats for a single frame of detections.
    Combines weapon presence, confidence, and spatial proximity to individuals.
    """
    if not frame_detections:
        return {
            "threat_score": 0.0,
            "threat_level": "SAFE",
            "threat_count": 0,
            "threat_objects": [],
            "armed_person_detected": False,
        }

    persons = [
        d for d in frame_detections
        if normalize_class_name(d.get("object", "")) == PERSON_CLASS
    ]

    max_score = 0.0
    threat_objects = []
    armed_person_detected = False

    for d in frame_detections:
        obj_name = d.get("object", "")
        conf = float(d.get("confidence", 0.0))
        bbox = d.get("bounding_box", {})

        base_weight, category = get_base_threat_weight(obj_name)
        if category == "NONE":
            continue

        # Item threat contribution = base_weight * confidence
        item_score = base_weight * (0.5 + 0.5 * conf)

        # Proximity fusion: check if any person is holding/near this threat object
        weapon_held_by_person = False
        if category in ("LETHAL_WEAPON", "BLUNT_WEAPON") and persons:
            for person in persons:
                p_bbox = person.get("bounding_box", {})
                if is_in_proximity(bbox, p_bbox):
                    weapon_held_by_person = True
                    armed_person_detected = True
                    break

        if weapon_held_by_person:
            # Multiplier for armed individual (escalates threat)
            item_score = min(1.0, item_score * 1.35)
            # Escalation if multiple people are present (crowd confrontation)
            if len(persons) >= 2:
                item_score = min(1.0, item_score + 0.10)

        threat_objects.append({
            "object": obj_name,
            "category": category,
            "confidence": round(conf, 3),
            "threat_score": round(item_score, 3),
            "held_by_person": weapon_held_by_person,
            "track_id": d.get("track_id"),
        })

        if item_score > max_score:
            max_score = item_score

    # Classify severity
    if max_score >= 0.75:
        level = "CRITICAL"
    elif max_score >= 0.50:
        level = "HIGH"
    elif max_score >= 0.25:
        level = "MEDIUM"
    elif max_score >= 0.10:
        level = "LOW"
    else:
        level = "SAFE"

    return {
        "threat_score": round(max_score, 3),
        "threat_level": level,
        "threat_count": len(threat_objects),
        "threat_objects": threat_objects,
        "armed_person_detected": armed_person_detected,
    }


def analyze_video_threats(
    detections: List[Dict[str, Any]],
    min_persistence_seconds: float = 0.5,
    cooldown_seconds: float = 2.0,
) -> Dict[str, Any]:
    """
    Performs temporal aggregation across all detections in the video.
    Filters single-frame blips and identifies distinct threat incidents.
    """
    if not detections:
        return {
            "max_threat_score": 0.0,
            "overall_threat_level": "SAFE",
            "total_incidents": 0,
            "incidents": [],
            "threat_summary": {
                "critical_events": 0,
                "high_events": 0,
                "medium_events": 0,
                "threat_objects_seen": {},
            },
        }

    # Group detections by frame
    frames_map = {}
    frame_timestamps = {}
    for d in detections:
        frame_idx = d.get("frame", 0)
        if frame_idx not in frames_map:
            frames_map[frame_idx] = []
            frame_timestamps[frame_idx] = d.get("timestamp", 0.0)
        frames_map[frame_idx].append(d)

    sorted_frames = sorted(frames_map.keys())

    # Frame-by-frame threat evaluation
    frame_scores = []
    for f_idx in sorted_frames:
        f_eval = score_frame_threat(frames_map[f_idx])
        ts = frame_timestamps[f_idx]
        frame_scores.append({
            "frame": f_idx,
            "timestamp": ts,
            **f_eval,
        })

    # Temporal aggregation into incidents
    incidents = []
    current_incident = None

    for f_data in frame_scores:
        score = f_data["threat_score"]
        ts = f_data["timestamp"]
        frame = f_data["frame"]
        level = f_data["threat_level"]

        is_threat = score >= 0.25  # Medium or higher threshold for an incident

        if is_threat:
            if current_incident is None:
                current_incident = {
                    "start_time": ts,
                    "end_time": ts,
                    "start_frame": frame,
                    "end_frame": frame,
                    "peak_score": score,
                    "peak_level": level,
                    "threat_types": set(o["object"] for o in f_data["threat_objects"]),
                    "categories": set(o["category"] for o in f_data["threat_objects"]),
                    "armed_person": f_data["armed_person_detected"],
                    "frame_count": 1,
                }
            else:
                # Update ongoing incident
                current_incident["end_time"] = ts
                current_incident["end_frame"] = frame
                current_incident["frame_count"] += 1
                if score > current_incident["peak_score"]:
                    current_incident["peak_score"] = score
                    current_incident["peak_level"] = level
                current_incident["armed_person"] = (
                    current_incident["armed_person"] or f_data["armed_person_detected"]
                )
                for o in f_data["threat_objects"]:
                    current_incident["threat_types"].add(o["object"])
                    current_incident["categories"].add(o["category"])
        else:
            if current_incident is not None:
                # Check if cooldown has elapsed before closing incident
                gap = ts - current_incident["end_time"]
                if gap > cooldown_seconds:
                    # Finalize incident
                    duration = current_incident["end_time"] - current_incident["start_time"]
                    if duration >= min_persistence_seconds or current_incident["peak_score"] >= 0.70:
                        current_incident["threat_types"] = sorted(list(current_incident["threat_types"]))
                        current_incident["categories"] = sorted(list(current_incident["categories"]))
                        current_incident["duration"] = round(duration, 2)
                        incidents.append(current_incident)
                    current_incident = None

    # Finalize last incident if still open
    if current_incident is not None:
        duration = current_incident["end_time"] - current_incident["start_time"]
        if duration >= min_persistence_seconds or current_incident["peak_score"] >= 0.70:
            current_incident["threat_types"] = sorted(list(current_incident["threat_types"]))
            current_incident["categories"] = sorted(list(current_incident["categories"]))
            current_incident["duration"] = round(duration, 2)
            incidents.append(current_incident)

    # Calculate overall metrics
    max_score = max((f["threat_score"] for f in frame_scores), default=0.0)
    if max_score >= 0.75:
        overall_level = "CRITICAL"
    elif max_score >= 0.50:
        overall_level = "HIGH"
    elif max_score >= 0.25:
        overall_level = "MEDIUM"
    elif max_score >= 0.10:
        overall_level = "LOW"
    else:
        overall_level = "SAFE"

    # Threat objects count
    threat_objects_seen = {}
    for f in frame_scores:
        for to in f.get("threat_objects", []):
            obj = to["object"]
            threat_objects_seen[obj] = threat_objects_seen.get(obj, 0) + 1

    return {
        "max_threat_score": round(max_score, 3),
        "overall_threat_level": overall_level,
        "total_incidents": len(incidents),
        "incidents": incidents,
        "threat_summary": {
            "critical_events": sum(1 for inc in incidents if inc["peak_level"] == "CRITICAL"),
            "high_events": sum(1 for inc in incidents if inc["peak_level"] == "HIGH"),
            "medium_events": sum(1 for inc in incidents if inc["peak_level"] == "MEDIUM"),
            "threat_objects_seen": threat_objects_seen,
        },
    }
