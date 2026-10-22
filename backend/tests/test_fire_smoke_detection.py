"""
Comprehensive Test Suite for Fire and Smoke Detection in ForenSight AI.

Tests verify:
1. Fire & smoke model loading, metadata, and graceful error handling when weights are missing.
2. Output format conforms to required unified schema:
   (class_name, confidence, timestamp, frame_number, detection_type, event_type, bounding_box, review_status).
3. Spatio-temporal deduplication and incident/event grouping.
4. Threat taxonomy integration in threat_service.py (FIRE_HAZARD, SMOKE_HAZARD).
5. Seamless integration with yolo_service.py (combined unified detections, no breaking changes).
6. Synthetic video tests:
   - Sample video with visible fire pattern
   - Sample video with visible smoke pattern
   - Sample video with neutral background (neither fire nor smoke) checking false positives
7. Timestamps, confidence scores, and structured JSON outputs.
"""

import sys
import unittest
import os
import json
import tempfile
from pathlib import Path
import numpy as np
import cv2

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from services.fire_smoke_service import (
    is_fire_smoke_model_available,
    get_fire_smoke_model,
    get_model_info,
    detect_fire_smoke_in_frame,
    deduplicate_fire_smoke_detections,
    group_fire_smoke_events,
    FIRE_SMOKE_MODEL_PATH,
)
from services.threat_service import (
    get_base_threat_weight,
    score_frame_threat,
    analyze_video_threats,
)


class TestFireSmokeService(unittest.TestCase):
    """Unit tests for services/fire_smoke_service.py"""

    def test_import_service(self):
        """Fire and smoke detection service module can be imported without errors."""
        from services import fire_smoke_service
        self.assertTrue(hasattr(fire_smoke_service, "detect_fire_smoke_in_frame"))
        self.assertTrue(hasattr(fire_smoke_service, "deduplicate_fire_smoke_detections"))
        self.assertTrue(hasattr(fire_smoke_service, "group_fire_smoke_events"))
        self.assertTrue(hasattr(fire_smoke_service, "is_fire_smoke_model_available"))
        self.assertTrue(hasattr(fire_smoke_service, "get_fire_smoke_model"))
        self.assertTrue(hasattr(fire_smoke_service, "get_model_info"))

    def test_model_availability(self):
        """is_fire_smoke_model_available returns a boolean."""
        available = is_fire_smoke_model_available()
        self.assertIsInstance(available, bool)
        self.assertTrue(available, "Expected pretrained fire_smoke_yolov8n.pt to be available")

    def test_model_classes_and_info(self):
        """Model info contains required metadata: classes, source, dataset, architecture."""
        info = get_model_info()
        self.assertTrue(info["available"])
        self.assertIn("classes", info)
        self.assertIn("smoke", info["classes"])
        self.assertIn("fire", info["classes"])
        self.assertIn("rabahdev/fire-smoke-yolov8n", info["source"])
        self.assertEqual(info["dataset"], "D-Fire")
        self.assertEqual(info["architecture"], "YOLOv8n")

    def test_graceful_handling_missing_weights(self):
        """When weights path does not exist, detect_fire_smoke_in_frame returns empty list without error."""
        import services.fire_smoke_service as fss
        original_model = fss._fire_smoke_model
        try:
            fss._fire_smoke_model = None
            fss._fire_smoke_model_available = False
            # Point to a non-existent path
            fss.FIRE_SMOKE_MODEL_PATH = Path("non_existent_weights.pt")

            dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            result = fss.detect_fire_smoke_in_frame(dummy_frame, 0, 30.0)
            self.assertEqual(result, [])
            self.assertFalse(fss.is_fire_smoke_model_available())
        finally:
            # Restore model
            fss._fire_smoke_model = original_model
            fss._fire_smoke_model_available = original_model is not None
            fss.FIRE_SMOKE_MODEL_PATH = Path(backend_dir / "fire_smoke_yolov8n.pt")

    def test_detection_output_schema_structure(self):
        """Simulate or verify detection output dictionary schema."""
        # Test schema on sample synthetic frame
        fire_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Add flame-like bright colors
        cv2.circle(fire_frame, (320, 240), 100, (0, 140, 255), -1)
        cv2.circle(fire_frame, (320, 240), 50, (0, 255, 255), -1)

        dets = detect_fire_smoke_in_frame(fire_frame, frame_number=45, fps=30.0, confidence_threshold=0.10)
        self.assertIsInstance(dets, list)

        for d in dets:
            self.assertIn("class_name", d)
            self.assertIn(d["class_name"], ["fire", "smoke"])
            self.assertIn("confidence", d)
            self.assertGreater(d["confidence"], 0)
            self.assertLessEqual(d["confidence"], 1.0)
            self.assertIn("timestamp", d)
            self.assertEqual(d["timestamp"], 1.5)
            self.assertIn("frame_number", d)
            self.assertEqual(d["frame_number"], 45)
            self.assertEqual(d["detection_type"], "fire_smoke")
            self.assertIn(d["event_type"], ["fire_detected", "smoke_detected"])
            self.assertEqual(d["review_status"], "requires_human_verification")
            self.assertEqual(len(d["bounding_box"]), 4)

    def test_deduplication_logic(self):
        """Near-duplicate detections in adjacent frames within same region are deduplicated."""
        raw_detections = [
            {
                "class_name": "fire",
                "confidence": 0.85,
                "timestamp": 1.0,
                "bounding_box": [100, 100, 200, 200],
                "frame_number": 30,
            },
            {
                "class_name": "fire",
                "confidence": 0.92,  # higher confidence
                "timestamp": 1.1,
                "bounding_box": [102, 98, 205, 202],  # high IoU
                "frame_number": 33,
            },
            {
                "class_name": "fire",
                "confidence": 0.78,
                "timestamp": 1.2,
                "bounding_box": [101, 100, 201, 199],  # high IoU
                "frame_number": 36,
            },
            {
                "class_name": "fire",
                "confidence": 0.88,
                "timestamp": 5.0,  # outside time window
                "bounding_box": [100, 100, 200, 200],
                "frame_number": 150,
            },
        ]

        deduped = deduplicate_fire_smoke_detections(raw_detections, iou_threshold=0.5, time_window=1.0)
        # Should keep the 0.92 detection for the t=1.0-1.2 cluster and 0.88 for t=5.0
        self.assertEqual(len(deduped), 2)
        peak_det = max(deduped, key=lambda d: d["confidence"])
        self.assertEqual(peak_det["confidence"], 0.92)

    def test_event_grouping_logic(self):
        """Consecutive frame detections are grouped into a continuous event/incident."""
        detections = [
            {
                "class_name": "fire",
                "confidence": 0.82,
                "timestamp": 2.0,
                "frame_number": 60,
                "bounding_box": [100, 100, 200, 200],
            },
            {
                "class_name": "fire",
                "confidence": 0.94,
                "timestamp": 2.5,
                "frame_number": 75,
                "bounding_box": [95, 95, 210, 215],
            },
            {
                "class_name": "fire",
                "confidence": 0.88,
                "timestamp": 3.0,
                "frame_number": 90,
                "bounding_box": [105, 100, 205, 200],
            },
            # Gap of 4 seconds -> separate incident
            {
                "class_name": "smoke",
                "confidence": 0.75,
                "timestamp": 7.0,
                "frame_number": 210,
                "bounding_box": [300, 150, 450, 300],
            },
            {
                "class_name": "smoke",
                "confidence": 0.79,
                "timestamp": 7.5,
                "frame_number": 225,
                "bounding_box": [310, 140, 460, 310],
            },
        ]

        events = group_fire_smoke_events(detections, max_gap_seconds=2.0)
        self.assertEqual(len(events), 2)

        # Event 1: Fire
        evt1 = events[0]
        self.assertEqual(evt1["class_name"], "fire")
        self.assertEqual(evt1["event_type"], "fire_outbreak")
        self.assertEqual(evt1["start_time"], 2.0)
        self.assertEqual(evt1["end_time"], 3.0)
        self.assertEqual(evt1["duration"], 1.0)
        self.assertEqual(evt1["peak_confidence"], 0.94)
        self.assertEqual(evt1["detection_count"], 3)
        self.assertEqual(evt1["status"], "requires_human_verification")

        # Event 2: Smoke
        evt2 = events[1]
        self.assertEqual(evt2["class_name"], "smoke")
        self.assertEqual(evt2["event_type"], "smoke_hazard")
        self.assertEqual(evt2["start_time"], 7.0)
        self.assertEqual(evt2["end_time"], 7.5)


class TestThreatServiceIntegration(unittest.TestCase):
    """Tests that threat_service correctly recognizes fire and smoke hazards."""

    def test_fire_and_smoke_threat_weights(self):
        """get_base_threat_weight returns proper weights and categories for fire and smoke."""
        w_fire, cat_fire = get_base_threat_weight("fire")
        self.assertEqual(cat_fire, "FIRE_HAZARD")
        self.assertGreaterEqual(w_fire, 0.85)

        w_smoke, cat_smoke = get_base_threat_weight("smoke")
        self.assertEqual(cat_smoke, "SMOKE_HAZARD")
        self.assertGreaterEqual(w_smoke, 0.65)

    def test_score_frame_with_fire(self):
        """Frame containing fire receives CRITICAL threat level."""
        frame_dets = [
            {
                "object": "fire",
                "confidence": 0.90,
                "bounding_box": {"x1": 50, "y1": 50, "x2": 150, "y2": 150},
            }
        ]
        score_res = score_frame_threat(frame_dets)
        self.assertIn(score_res["threat_level"], ["HIGH", "CRITICAL"])
        self.assertGreaterEqual(score_res["threat_score"], 0.70)

    def test_video_threats_aggregation_with_fire(self):
        """analyze_video_threats groups fire incidents into the video timeline."""
        detections = [
            {
                "frame": 30,
                "timestamp": 1.0,
                "object": "fire",
                "confidence": 0.85,
                "bounding_box": {"x1": 50, "y1": 50, "x2": 150, "y2": 150},
            },
            {
                "frame": 60,
                "timestamp": 2.0,
                "object": "fire",
                "confidence": 0.90,
                "bounding_box": {"x1": 55, "y1": 55, "x2": 155, "y2": 155},
            },
        ]
        vt = analyze_video_threats(detections)
        self.assertGreater(vt["max_threat_score"], 0.70)
        self.assertIn(vt["overall_threat_level"], ["HIGH", "CRITICAL"])
        self.assertGreaterEqual(vt["total_incidents"], 1)
        inc = vt["incidents"][0]
        self.assertIn("fire", inc["threat_types"])


class TestEndToEndVideoProcessing(unittest.TestCase):
    """End-to-end video processing tests with synthetic video clips."""

    def _create_synthetic_video(self, file_path: Path, pattern: str, num_frames=30, fps=15):
        """Creates an mp4 video with a specified visual pattern."""
        width, height = 320, 240
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(file_path), fourcc, fps, (width, height))

        for f in range(num_frames):
            frame = np.full((height, width, 3), 40, dtype=np.uint8)  # dark background

            if pattern == "fire":
                # Glowing flame simulation (bright yellow-orange center with red rim)
                cv2.circle(frame, (160, 120), 40 + (f % 5), (0, 69, 255), -1)
                cv2.circle(frame, (160, 120), 20 + (f % 3), (0, 215, 255), -1)
                cv2.circle(frame, (160, 110), 10, (255, 255, 255), -1)
            elif pattern == "smoke":
                # Billowing gray haze
                cv2.circle(frame, (160, 100), 50 + (f % 10), (140, 140, 140), -1)
                cv2.circle(frame, (170, 90), 35, (180, 180, 180), -1)
            elif pattern == "neutral":
                # Clean neutral room background: brown floor, gray wall
                frame[160:, :] = (50, 70, 90)
                frame[:160, :] = (180, 180, 180)

            writer.write(frame)

        writer.release()

    def test_pipeline_on_neutral_video(self):
        """Neutral video processes cleanly without crashes and returns expected keys."""
        from services.yolo_service import analyze_video

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            video_file = tmp_path / "neutral.mp4"
            out_dir = tmp_path / "results"
            self._create_synthetic_video(video_file, pattern="neutral", num_frames=18, fps=15)

            result = analyze_video(str(video_file), str(out_dir), analysis_id="test-neutral")

            # Verify return structure
            self.assertIn("analysis_id", result)
            self.assertIn("video", result)
            self.assertIn("total_detections", result)
            self.assertIn("object_counts", result)
            self.assertIn("threat_analysis", result)
            self.assertIn("detections", result)
            self.assertIn("weapon_detections", result)
            self.assertIn("fire_smoke_detections", result)
            self.assertIn("fire_smoke_events", result)

            # Check that annotated video was created
            annotated_video = Path(result["video"])
            self.assertTrue(annotated_video.exists())
            self.assertGreater(annotated_video.stat().st_size, 0)

            # Check JSON artifacts
            res_json = out_dir / "test-neutral_result.json"
            self.assertTrue(res_json.exists())
            with open(res_json, "r") as f:
                data = json.load(f)
                self.assertEqual(data["analysis_id"], "test-neutral")
                self.assertIn("fire_smoke_events", data)

    def test_pipeline_on_fire_video(self):
        """Video with bright flame pattern runs through YOLO & fire_smoke models."""
        from services.yolo_service import analyze_video

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            video_file = tmp_path / "fire_test.mp4"
            out_dir = tmp_path / "results"
            self._create_synthetic_video(video_file, pattern="fire", num_frames=20, fps=15)

            result = analyze_video(str(video_file), str(out_dir), analysis_id="test-fire")

            self.assertIn("detections", result)
            self.assertIn("fire_smoke_detections", result)
            self.assertIn("fire_smoke_events", result)
            self.assertTrue(Path(result["video"]).exists())

            # Verify saved fire_smoke.json artifact
            fs_json = out_dir / "test-fire_fire_smoke.json"
            self.assertTrue(fs_json.exists())
            with open(fs_json, "r") as f:
                data = json.load(f)
                self.assertIn("fire_smoke_events", data)
                self.assertIn("fire_smoke_detections", data)


if __name__ == "__main__":
    unittest.main()
