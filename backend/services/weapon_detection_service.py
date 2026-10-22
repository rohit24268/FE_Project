"""
Weapon Detection Service for ForenSight AI.

Uses a ready-made, lightweight YOLO11n model fine-tuned for weapon detection
(guns, knives) from:
    https://huggingface.co/cosgun99/gun-knife-yolo11n

Model weights file: weapon_yolo11n.pt (downloaded from HuggingFace Hub)
License: MIT
Task: Object Detection (detect)

Supported classes:
    0: gun
    1: knife

Features:
    - Pretrained YOLO11n inference for high-speed CCTV video frame analysis.
    - Configurable Sliced Aided Hyper Inference (SAHI) for detecting small
      weapons in high-resolution CCTV footage without writing temporary files.
    - Spatio-temporal deduplication across consecutive video frames.
    - Graceful fallback when weights are missing (returns empty list, logs warning).
    - Preserves existing YOLO11n general object detection completely intact.
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

# Primary model: cosgun99/gun-knife-yolo11n (YOLO11n, MIT license)
_DEFAULT_YOLO11_PATH = _BACKEND_DIR / "weapon_yolo11n.pt"
# Backward-compatibility fallback
_FALLBACK_YOLOV8_PATH = _BACKEND_DIR / "weapon_yolov8n.pt"

_ENV_MODEL_PATH = os.environ.get("WEAPON_MODEL_PATH", "").strip()

if _ENV_MODEL_PATH:
    WEAPON_MODEL_PATH = Path(_ENV_MODEL_PATH)
elif _DEFAULT_YOLO11_PATH.exists():
    WEAPON_MODEL_PATH = _DEFAULT_YOLO11_PATH
elif _FALLBACK_YOLOV8_PATH.exists():
    WEAPON_MODEL_PATH = _FALLBACK_YOLOV8_PATH
else:
    WEAPON_MODEL_PATH = _DEFAULT_YOLO11_PATH

# Target weapon classes
WEAPON_CLASSES = {"gun", "knife", "pistol", "rifle", "weapon", "explosive", "grenade"}

# SAHI Configuration
USE_SAHI = os.environ.get("WEAPON_USE_SAHI", "false").lower() in ("true", "1", "yes")
SAHI_SLICE_HEIGHT = int(os.environ.get("SAHI_SLICE_HEIGHT", "360"))
SAHI_SLICE_WIDTH = int(os.environ.get("SAHI_SLICE_WIDTH", "360"))
SAHI_OVERLAP_RATIO = float(os.environ.get("SAHI_OVERLAP_RATIO", "0.2"))

# --------------------------------------------------
# MODEL SINGLETONS
# --------------------------------------------------

_weapon_model: Optional[YOLO] = None
_sahi_model: Any = None
_weapon_model_available: bool = False


def _load_weapon_model() -> Optional[YOLO]:
    """Load the weapon detection model once (singleton). Returns None if missing."""
    global _weapon_model, _weapon_model_available

    if _weapon_model is not None:
        return _weapon_model

    if not WEAPON_MODEL_PATH.exists():
        print(
            f"[ForenSight AI] WARNING: Weapon model weights not found at "
            f"{WEAPON_MODEL_PATH}. Weapon detection is disabled.\n"
            f"  Download instructions for cosgun99/gun-knife-yolo11n:\n"
            f"    python -c \"import requests; r=requests.get('https://huggingface.co/cosgun99/gun-knife-yolo11n/resolve/main/best.pt'); "
            f"open(r'{WEAPON_MODEL_PATH}', 'wb').write(r.content)\"\n"
        )
        _weapon_model_available = False
        return None

    try:
        _weapon_model = YOLO(str(WEAPON_MODEL_PATH))
        _weapon_model_available = True
        detected_classes = list(_weapon_model.names.values()) if _weapon_model.names else []
        print(
            f"[ForenSight AI] Weapon detection model loaded from {WEAPON_MODEL_PATH}\n"
            f"  Architecture: YOLO11n | Supported classes: {detected_classes}"
        )
        return _weapon_model
    except Exception as e:
        print(f"[ForenSight AI] ERROR: Failed to load weapon model: {e}")
        _weapon_model_available = False
        return None


def _get_sahi_detection_model():
    """Lazily load and return the SAHI AutoDetectionModel wrapper."""
    global _sahi_model
    if _sahi_model is not None:
        return _sahi_model

    if not WEAPON_MODEL_PATH.exists():
        return None

    try:
        from sahi import AutoDetectionModel
        _sahi_model = AutoDetectionModel.from_pretrained(
            model_type="ultralytics",
            model_path=str(WEAPON_MODEL_PATH),
            confidence_threshold=0.35,
            device="cpu",
        )
        return _sahi_model
    except Exception as e:
        print(f"[ForenSight AI] WARNING: Could not initialize SAHI detection model: {e}")
        return None


def is_weapon_model_available() -> bool:
    """Check if the weapon model has been loaded successfully."""
    return _weapon_model_available


def get_weapon_model() -> Optional[YOLO]:
    """Return the loaded weapon model, or None if unavailable."""
    return _load_weapon_model()


def get_model_info() -> Dict[str, Any]:
    """Return metadata about the currently loaded weapon model."""
    model = get_weapon_model()
    return {
        "model_path": str(WEAPON_MODEL_PATH),
        "available": is_weapon_model_available(),
        "sahi_enabled": USE_SAHI,
        "classes": list(model.names.values()) if (model and model.names) else [],
        "source": "cosgun99/gun-knife-yolo11n (HuggingFace)",
        "license": "MIT",
    }


# --------------------------------------------------
# FRAME-LEVEL WEAPON DETECTION
# --------------------------------------------------

def detect_weapons_in_frame(
    frame: np.ndarray,
    frame_number: int,
    fps: float,
    confidence_threshold: float = 0.35,
    image_size: int = 640,
    use_sahi: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """
    Run weapon detection on a single video frame.

    Supports both standard full-frame YOLO inference (fast, ~100ms)
    and optional SAHI sliced inference (for high-res frames with small weapons).

    Returns a list of weapon detection dicts matching the required format:
        {
            "class_name": "gun",
            "confidence": 0.91,
            "timestamp": 12.4,
            "bounding_box": [x1, y1, x2, y2],
            "frame_number": 372,
            "review_status": "requires_human_review"
        }
    """
    model = get_weapon_model()
    if model is None:
        return []

    should_use_sahi = USE_SAHI if use_sahi is None else use_sahi

    # Execute SAHI sliced inference if requested
    if should_use_sahi:
        sahi_model = _get_sahi_detection_model()
        if sahi_model is not None:
            return _detect_weapons_sahi(
                frame,
                frame_number,
                fps,
                confidence_threshold,
                sahi_model,
            )

    # Standard full-frame inference (default, fast, memory-safe)
    return _detect_weapons_standard(
        frame,
        frame_number,
        fps,
        confidence_threshold,
        image_size,
        model,
    )


def _detect_weapons_standard(
    frame: np.ndarray,
    frame_number: int,
    fps: float,
    confidence_threshold: float,
    image_size: int,
    model: YOLO,
) -> List[Dict[str, Any]]:
    """Standard full-frame YOLO inference."""
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
        print(f"[ForenSight AI] Weapon detection error on frame {frame_number}: {e}")
        return []

    detections = []
    for result in results:
        if result.boxes is None:
            continue

        for box in result.boxes:
            class_id = int(box.cls[0])
            class_name = model.names[class_id].lower()
            confidence = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            timestamp = round(frame_number / fps, 3) if fps > 0 else 0.0

            detections.append({
                "class_name": class_name,
                "confidence": round(confidence, 4),
                "timestamp": timestamp,
                "bounding_box": [x1, y1, x2, y2],
                "frame_number": frame_number,
                "review_status": "requires_human_review",
            })

    return detections


def _detect_weapons_sahi(
    frame: np.ndarray,
    frame_number: int,
    fps: float,
    confidence_threshold: float,
    sahi_model: Any,
) -> List[Dict[str, Any]]:
    """SAHI sliced inference on in-memory frame without saving to disk."""
    try:
        from sahi.predict import get_sliced_prediction

        sahi_model.confidence_threshold = confidence_threshold
        result = get_sliced_prediction(
            frame,
            sahi_model,
            slice_height=SAHI_SLICE_HEIGHT,
            slice_width=SAHI_SLICE_WIDTH,
            overlap_height_ratio=SAHI_OVERLAP_RATIO,
            overlap_width_ratio=SAHI_OVERLAP_RATIO,
            verbose=0,
        )
    except Exception as e:
        print(f"[ForenSight AI] SAHI weapon detection error on frame {frame_number}: {e}")
        return []

    detections = []
    timestamp = round(frame_number / fps, 3) if fps > 0 else 0.0

    for pred in result.object_prediction_list:
        class_name = pred.category.name.lower()
        confidence = float(pred.score.value)
        bbox = pred.bbox.to_xyxy()
        x1, y1, x2, y2 = [int(round(coord)) for coord in bbox]

        detections.append({
            "class_name": class_name,
            "confidence": round(confidence, 4),
            "timestamp": timestamp,
            "bounding_box": [x1, y1, x2, y2],
            "frame_number": frame_number,
            "review_status": "requires_human_review",
        })

    return detections


# --------------------------------------------------
# SPATIO-TEMPORAL DEDUPLICATION
# --------------------------------------------------

def deduplicate_weapon_detections(
    detections: List[Dict[str, Any]],
    iou_threshold: float = 0.50,
    time_window: float = 1.0,
) -> List[Dict[str, Any]]:
    """
    Remove near-duplicate weapon detections appearing in consecutive frames
    with overlapping bounding boxes and the same class.

    Keeps the detection with the highest confidence within each time window
    per class and spatial region.
    """
    if not detections:
        return []

    # Sort by timestamp then confidence (descending)
    sorted_dets = sorted(
        detections,
        key=lambda d: (d["timestamp"], -d["confidence"]),
    )

    kept: List[Dict[str, Any]] = []

    for det in sorted_dets:
        is_duplicate = False
        for existing in kept:
            if det["class_name"] != existing["class_name"]:
                continue
            if abs(det["timestamp"] - existing["timestamp"]) > time_window:
                continue
            # Check IoU
            iou = _compute_iou_list(det["bounding_box"], existing["bounding_box"])
            if iou >= iou_threshold:
                is_duplicate = True
                break

        if not is_duplicate:
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
# INITIALIZATION — attempt to load model at import time
# --------------------------------------------------
_load_weapon_model()
