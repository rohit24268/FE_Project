"""
Fire and Smoke Detection Service for ForenSight AI.

Uses a verified, lightweight pretrained YOLOv8n model fine-tuned for fire
and smoke detection from Hugging Face:
    https://huggingface.co/rabahdev/fire-smoke-yolov8n

Dataset: D-Fire benchmark dataset (specifically designed for fire & smoke surveillance).
Model weights file: fire_smoke_yolov8n.pt (downloaded from Hugging Face Hub)
Architecture: YOLOv8n (detect)
Ultralytics support: Native YOLO weights, compatible with Ultralytics 8.x

Supported classes:
    0: smoke
    1: fire

Features:
    - Pretrained YOLOv8n inference for high-speed CCTV video frame analysis.
    - Confidence scoring, bounding boxes, timestamps, and frame numbers.
    - Spatio-temporal event grouping (groups consecutive detections into persistent
      incidents with start_time, end_time, duration, and peak confidence).
    - Spatio-temporal frame-level deduplication.
    - Singleton model loading (loaded once at startup / import, reused across frames).
    - Robust error handling: graceful fallback when weights are missing
      (logs clear instructions, returns empty list without crashing application).
    - Unified detection output conforming to ForenSight AI schema.
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional

import numpy as np
import torch
from ultralytics import YOLO

# Automatic device selection (GPU if available, otherwise safe CPU)
_DEVICE = 0 if torch.cuda.is_available() else "cpu"

# --------------------------------------------------
# CONFIGURATION & MODEL RESOLUTION
# --------------------------------------------------

_BACKEND_DIR = Path(__file__).resolve().parent.parent

# Primary model: rabahdev/fire-smoke-yolov8n (YOLOv8n trained on D-Fire)
_DEFAULT_MODEL_PATH = _BACKEND_DIR / "fire_smoke_yolov8n.pt"
_FALLBACK_MODEL_PATH = _BACKEND_DIR / "fire_yolov8n.pt"

_ENV_MODEL_PATH = os.environ.get("FIRE_SMOKE_MODEL_PATH", "").strip()

if _ENV_MODEL_PATH:
    FIRE_SMOKE_MODEL_PATH = Path(_ENV_MODEL_PATH)
elif _DEFAULT_MODEL_PATH.exists():
    FIRE_SMOKE_MODEL_PATH = _DEFAULT_MODEL_PATH
elif _FALLBACK_MODEL_PATH.exists():
    FIRE_SMOKE_MODEL_PATH = _FALLBACK_MODEL_PATH
else:
    FIRE_SMOKE_MODEL_PATH = _DEFAULT_MODEL_PATH

# Target classes
FIRE_SMOKE_CLASSES = {"fire", "smoke", "flame"}

# Default confidence threshold (configurable via env)
DEFAULT_CONFIDENCE = float(os.environ.get("FIRE_SMOKE_CONFIDENCE", "0.35"))

# --------------------------------------------------
# MODEL SINGLETON
# --------------------------------------------------

_fire_smoke_model: Optional[YOLO] = None
_fire_smoke_model_available: bool = False


def _load_fire_smoke_model() -> Optional[YOLO]:
    """
    Load the fire and smoke detection model once (singleton).
    Returns None if weights are missing, logging clear instructions without crashing.
    """
    global _fire_smoke_model, _fire_smoke_model_available

    if _fire_smoke_model is not None:
        return _fire_smoke_model

    if not FIRE_SMOKE_MODEL_PATH.exists():
        print(
            f"[ForenSight AI] WARNING: Fire & smoke model weights not found at "
            f"{FIRE_SMOKE_MODEL_PATH}.\n"
            f"  Fire and smoke detection is currently disabled.\n"
            f"  To enable, download verified weights from HuggingFace (rabahdev/fire-smoke-yolov8n):\n"
            f"    python -c \"import urllib.request; "
            f"urllib.request.urlretrieve('https://huggingface.co/rabahdev/fire-smoke-yolov8n/resolve/main/best.pt', "
            f"r'{FIRE_SMOKE_MODEL_PATH}')\"\n"
        )
        _fire_smoke_model_available = False
        return None

    try:
        _fire_smoke_model = YOLO(str(FIRE_SMOKE_MODEL_PATH))
        _fire_smoke_model_available = True
        detected_classes = (
            list(_fire_smoke_model.names.values())
            if _fire_smoke_model.names
            else []
        )
        print(
            f"[ForenSight AI] Fire and Smoke detection model loaded from {FIRE_SMOKE_MODEL_PATH}\n"
            f"  Architecture: YOLOv8n | Supported classes: {detected_classes} | Source: rabahdev/fire-smoke-yolov8n (D-Fire)"
        )
        return _fire_smoke_model
    except Exception as e:
        print(f"[ForenSight AI] ERROR: Failed to load fire and smoke model: {e}")
        _fire_smoke_model_available = False
        return None


def is_fire_smoke_model_available() -> bool:
    """Check if the fire and smoke detection model has been loaded successfully."""
    return _fire_smoke_model_available


def get_fire_smoke_model() -> Optional[YOLO]:
    """Return the loaded fire/smoke model instance, or None if unavailable."""
    return _load_fire_smoke_model()


def get_model_info() -> Dict[str, Any]:
    """Return metadata about the currently loaded fire & smoke detection model."""
    model = get_fire_smoke_model()
    return {
        "model_path": str(FIRE_SMOKE_MODEL_PATH),
        "available": is_fire_smoke_model_available(),
        "classes": list(model.names.values()) if (model and model.names) else [],
        "source": "rabahdev/fire-smoke-yolov8n (Hugging Face)",
        "dataset": "D-Fire",
        "architecture": "YOLOv8n",
        "license": "Open Source / MIT compatible",
        "default_confidence": DEFAULT_CONFIDENCE,
    }


# --------------------------------------------------
# FRAME-LEVEL DETECTION
# --------------------------------------------------

def detect_fire_smoke_in_frame(
    frame: np.ndarray,
    frame_number: int,
    fps: float,
    confidence_threshold: float = DEFAULT_CONFIDENCE,
    image_size: int = 640,
) -> List[Dict[str, Any]]:
    """
    Run fire and smoke detection on a single video frame.

    Args:
        frame: BGR image as numpy array.
        frame_number: Current frame index in video.
        fps: Frames per second of the video.
        confidence_threshold: Minimum detection confidence score.
        image_size: Inference resolution (default 640).

    Returns:
        List of detection dictionaries conforming to ForenSight AI schema:
        [
            {
                "class_name": "fire",
                "confidence": 0.89,
                "timestamp": 4.5,
                "bounding_box": [x1, y1, x2, y2],
                "frame_number": 135,
                "detection_type": "fire_smoke",
                "event_type": "fire_detected",
                "review_status": "requires_human_verification",
            },
            ...
        ]
    """
    model = get_fire_smoke_model()
    if model is None:
        return []

    try:
        with torch.inference_mode():
            results = model(
                frame,
                conf=confidence_threshold,
                imgsz=image_size,
                verbose=False,
                device=_DEVICE,
            )
    except Exception as e:
        print(f"[ForenSight AI] Fire/smoke inference error on frame {frame_number}: {e}")
        return []

    detections: List[Dict[str, Any]] = []

    for result in results:
        if result.boxes is None:
            continue

        for box in result.boxes:
            class_id = int(box.cls[0])
            raw_name = model.names.get(class_id, "unknown").lower()

            # Normalize to 'fire' or 'smoke'
            if "fire" in raw_name or "flame" in raw_name:
                class_name = "fire"
            elif "smoke" in raw_name:
                class_name = "smoke"
            else:
                class_name = raw_name

            confidence = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            timestamp = round(frame_number / fps, 3) if fps > 0 else 0.0

            detections.append({
                "class_name": class_name,
                "confidence": round(confidence, 4),
                "timestamp": timestamp,
                "bounding_box": [x1, y1, x2, y2],
                "frame_number": frame_number,
                "detection_type": "fire_smoke",
                "event_type": f"{class_name}_detected",
                "review_status": "requires_human_verification",
            })

    return detections


# --------------------------------------------------
# SPATIO-TEMPORAL DEDUPLICATION
# --------------------------------------------------

def deduplicate_fire_smoke_detections(
    detections: List[Dict[str, Any]],
    iou_threshold: float = 0.50,
    time_window: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    Remove near-duplicate fire/smoke detections across consecutive frames
    with high spatial overlap and same class. Keeps the highest confidence
    detection per region and class within each time window.
    """
    if not detections:
        return []

    sorted_dets = sorted(
        detections,
        key=lambda d: (d["timestamp"], -d["confidence"]),
    )

    kept: List[Dict[str, Any]] = []

    for det in sorted_dets:
        duplicate_idx = -1
        for idx, existing in enumerate(kept):
            if det["class_name"] != existing["class_name"]:
                continue
            if abs(det["timestamp"] - existing["timestamp"]) > time_window:
                continue
            iou = _compute_iou_list(det["bounding_box"], existing["bounding_box"])
            if iou >= iou_threshold:
                duplicate_idx = idx
                break

        if duplicate_idx != -1:
            if det["confidence"] > kept[duplicate_idx]["confidence"]:
                kept[duplicate_idx] = det
        else:
            kept.append(det)

    return kept


def _compute_iou_list(box1: list, box2: list) -> float:
    """Compute IoU between two [x1, y1, x2, y2] bounding boxes."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    if intersection == 0:
        return 0.0

    area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
    area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union = area1 + area2 - intersection
    return intersection / union if union > 0 else 0.0


# --------------------------------------------------
# EVENT GROUPING (INCIDENT TIMELINE AGGREGATION)
# --------------------------------------------------

def group_fire_smoke_events(
    detections: List[Dict[str, Any]],
    max_gap_seconds: float = 2.0,
    min_detections: int = 2,
) -> List[Dict[str, Any]]:
    """
    Aggregate raw frame-level fire and smoke detections into continuous incidents
    with start time, end time, duration, peak confidence, and spatial envelope.

    Prevents reporting every single frame as an independent incident.

    Returns:
        List of structured incident event dicts:
        [
            {
                "event_id": "FS-EVT-001",
                "class_name": "fire",
                "event_type": "fire_outbreak",
                "start_time": 4.5,
                "end_time": 8.2,
                "duration": 3.7,
                "start_frame": 135,
                "end_frame": 246,
                "peak_confidence": 0.92,
                "detection_count": 28,
                "bounding_box": [x1, y1, x2, y2],
                "description": "Potential fire outbreak detected from 4.50s to 8.20s (peak conf 92.0%)",
                "status": "requires_human_verification",
            },
            ...
        ]
    """
    if not detections:
        return []

    # Sort detections chronologically
    sorted_dets = sorted(detections, key=lambda d: d.get("timestamp", 0.0))

    events: List[Dict[str, Any]] = []
    current_cluster: List[Dict[str, Any]] = []
    current_class: Optional[str] = None

    def _finalize_cluster(cluster: List[Dict[str, Any]], evt_index: int) -> Optional[Dict[str, Any]]:
        if not cluster:
            return None

        # Accept if at least min_detections or single high-confidence detection (>= 0.70)
        max_conf = max(d["confidence"] for d in cluster)
        if len(cluster) < min_detections and max_conf < 0.70:
            return None

        start_t = cluster[0]["timestamp"]
        end_t = cluster[-1]["timestamp"]
        duration = round(max(0.0, end_t - start_t), 2)
        classes_present = set(d["class_name"] for d in cluster)

        if "fire" in classes_present and "smoke" in classes_present:
            primary_class = "fire_and_smoke"
            event_type = "fire_and_smoke_outbreak"
        elif "fire" in classes_present:
            primary_class = "fire"
            event_type = "fire_outbreak"
        else:
            primary_class = "smoke"
            event_type = "smoke_hazard"

        # Bounding box envelope (union of all boxes in cluster)
        min_x1 = min(d["bounding_box"][0] for d in cluster)
        min_y1 = min(d["bounding_box"][1] for d in cluster)
        max_x2 = max(d["bounding_box"][2] for d in cluster)
        max_y2 = max(d["bounding_box"][3] for d in cluster)

        desc = (
            f"Potential {primary_class.replace('_', ' ')} incident detected from "
            f"{start_t:.2f}s to {end_t:.2f}s (duration: {duration}s, "
            f"peak confidence: {max_conf * 100:.1f}%). Requires human verification."
        )

        return {
            "event_id": f"FS-EVT-{evt_index:03d}",
            "class_name": primary_class,
            "event_type": event_type,
            "start_time": round(start_t, 2),
            "end_time": round(end_t, 2),
            "duration": duration,
            "start_frame": cluster[0]["frame_number"],
            "end_frame": cluster[-1]["frame_number"],
            "peak_confidence": round(max_conf, 4),
            "detection_count": len(cluster),
            "bounding_box": [min_x1, min_y1, max_x2, max_y2],
            "description": desc,
            "status": "requires_human_verification",
        }

    evt_counter = 1
    for det in sorted_dets:
        if not current_cluster:
            current_cluster.append(det)
            current_class = det["class_name"]
            continue

        last_det = current_cluster[-1]
        time_gap = det["timestamp"] - last_det["timestamp"]

        # If gap is within max_gap_seconds, group into the same incident
        if time_gap <= max_gap_seconds:
            current_cluster.append(det)
        else:
            # Finalize previous incident
            event_dict = _finalize_cluster(current_cluster, evt_counter)
            if event_dict:
                events.append(event_dict)
                evt_counter += 1
            current_cluster = [det]
            current_class = det["class_name"]

    if current_cluster:
        event_dict = _finalize_cluster(current_cluster, evt_counter)
        if event_dict:
            events.append(event_dict)

    return events


# --------------------------------------------------
# INITIALIZATION — attempt singleton load at import
# --------------------------------------------------
_load_fire_smoke_model()
