"""
Tests for the weapon detection service.

Tests verify:
1. Weapon model loading and graceful handling when weights are missing.
2. Weapon detection output format (class_name, confidence, timestamp, bounding_box, frame_number, review_status).
3. Deduplication logic.
4. Integration with the existing YOLO service (weapon_detections key in result).
5. Existing API endpoints remain functional.
6. No frontend files have been modified.
"""

import sys
import unittest
import os
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


class TestWeaponDetectionService(unittest.TestCase):
    """Unit tests for services/weapon_detection_service.py"""

    def test_import_service(self):
        """Weapon detection service module can be imported without errors."""
        from services import weapon_detection_service
        self.assertTrue(hasattr(weapon_detection_service, "detect_weapons_in_frame"))
        self.assertTrue(hasattr(weapon_detection_service, "deduplicate_weapon_detections"))
        self.assertTrue(hasattr(weapon_detection_service, "is_weapon_model_available"))
        self.assertTrue(hasattr(weapon_detection_service, "get_weapon_model"))

    def test_weapon_classes_defined(self):
        """WEAPON_CLASSES constant contains expected weapon types."""
        from services.weapon_detection_service import WEAPON_CLASSES
        self.assertIn("gun", WEAPON_CLASSES)
        self.assertIn("knife", WEAPON_CLASSES)

    def test_model_availability_flag(self):
        """is_weapon_model_available returns a boolean."""
        from services.weapon_detection_service import is_weapon_model_available
        result = is_weapon_model_available()
        self.assertIsInstance(result, bool)

    def test_detect_weapons_returns_list_when_model_missing(self):
        """detect_weapons_in_frame returns empty list when model is unavailable."""
        from services.weapon_detection_service import is_weapon_model_available
        import numpy as np

        if not is_weapon_model_available():
            from services.weapon_detection_service import detect_weapons_in_frame
            dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            result = detect_weapons_in_frame(dummy_frame, 0, 30.0)
            self.assertIsInstance(result, list)
            self.assertEqual(len(result), 0)

    def test_detection_output_format(self):
        """When model is available, detections have the correct JSON structure."""
        from services.weapon_detection_service import (
            is_weapon_model_available,
            detect_weapons_in_frame,
        )
        import numpy as np

        if not is_weapon_model_available():
            self.skipTest("Weapon model weights not available")

        # Use a blank frame — may or may not produce detections
        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detect_weapons_in_frame(dummy_frame, 100, 30.0)
        self.assertIsInstance(result, list)

        # If any detections, verify format
        for det in result:
            self.assertIn("class_name", det)
            self.assertIn("confidence", det)
            self.assertIn("timestamp", det)
            self.assertIn("bounding_box", det)
            self.assertIn("frame_number", det)
            self.assertIn("review_status", det)
            self.assertEqual(det["review_status"], "requires_human_review")
            self.assertIsInstance(det["bounding_box"], list)
            self.assertEqual(len(det["bounding_box"]), 4)
            self.assertEqual(det["frame_number"], 100)
            self.assertGreater(det["confidence"], 0)
            self.assertLessEqual(det["confidence"], 1)

    def test_get_model_info(self):
        """Model info contains required metadata: classes, source, license."""
        from services.weapon_detection_service import get_model_info
        info = get_model_info()
        self.assertIn("classes", info)
        self.assertIn("source", info)
        self.assertIn("license", info)
        self.assertEqual(info["license"], "MIT")

    def test_sahi_sliced_inference_on_frame(self):
        """SAHI sliced inference runs successfully on in-memory numpy frames."""
        import numpy as np
        from services.weapon_detection_service import (
            is_weapon_model_available,
            detect_weapons_in_frame,
        )
        if not is_weapon_model_available():
            self.skipTest("Weapon model not available")

        dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        # Run with use_sahi=True
        result = detect_weapons_in_frame(dummy_frame, frame_number=1, fps=30.0, use_sahi=True)
        self.assertIsInstance(result, list)

    def test_model_missing_graceful_handling(self):
        """When weapon model path is invalid, service handles gracefully."""
        import numpy as np
        from unittest.mock import patch
        from services import weapon_detection_service

        with patch.object(weapon_detection_service, "get_weapon_model", return_value=None):
            dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
            result = weapon_detection_service.detect_weapons_in_frame(dummy_frame, 1, 30.0)
            self.assertEqual(result, [])

    def test_deduplicate_empty_list(self):
        """Deduplication of empty list returns empty list."""
        from services.weapon_detection_service import deduplicate_weapon_detections
        result = deduplicate_weapon_detections([])
        self.assertEqual(result, [])

    def test_deduplicate_removes_duplicates(self):
        """Near-duplicate detections in consecutive frames are collapsed."""
        from services.weapon_detection_service import deduplicate_weapon_detections

        detections = [
            {
                "class_name": "gun",
                "confidence": 0.90,
                "timestamp": 1.0,
                "bounding_box": [100, 100, 200, 200],
                "frame_number": 30,
                "review_status": "requires_human_review",
            },
            {
                "class_name": "gun",
                "confidence": 0.88,
                "timestamp": 1.1,
                "bounding_box": [102, 98, 198, 202],  # nearly same box
                "frame_number": 33,
                "review_status": "requires_human_review",
            },
        ]

        result = deduplicate_weapon_detections(detections, iou_threshold=0.5, time_window=1.0)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence"], 0.90)  # higher confidence kept

    def test_deduplicate_keeps_different_classes(self):
        """Detections of different weapon classes are not collapsed."""
        from services.weapon_detection_service import deduplicate_weapon_detections

        detections = [
            {
                "class_name": "gun",
                "confidence": 0.90,
                "timestamp": 1.0,
                "bounding_box": [100, 100, 200, 200],
                "frame_number": 30,
                "review_status": "requires_human_review",
            },
            {
                "class_name": "knife",
                "confidence": 0.85,
                "timestamp": 1.0,
                "bounding_box": [100, 100, 200, 200],
                "frame_number": 30,
                "review_status": "requires_human_review",
            },
        ]

        result = deduplicate_weapon_detections(detections, iou_threshold=0.5, time_window=1.0)
        self.assertEqual(len(result), 2)

    def test_deduplicate_keeps_far_apart_detections(self):
        """Detections far apart in time are not collapsed."""
        from services.weapon_detection_service import deduplicate_weapon_detections

        detections = [
            {
                "class_name": "gun",
                "confidence": 0.90,
                "timestamp": 1.0,
                "bounding_box": [100, 100, 200, 200],
                "frame_number": 30,
                "review_status": "requires_human_review",
            },
            {
                "class_name": "gun",
                "confidence": 0.88,
                "timestamp": 10.0,
                "bounding_box": [100, 100, 200, 200],
                "frame_number": 300,
                "review_status": "requires_human_review",
            },
        ]

        result = deduplicate_weapon_detections(detections, iou_threshold=0.5, time_window=1.0)
        self.assertEqual(len(result), 2)


class TestExistingYoloServicePreserved(unittest.TestCase):
    """Verify that the existing YOLO service interface is unchanged."""

    def test_yolo_model_loads(self):
        """The existing yolo11n.pt model still loads correctly."""
        from services.yolo_service import model, MODEL_PATH
        self.assertIsNotNone(model)
        self.assertTrue(MODEL_PATH.exists())

    def test_analyze_video_function_exists(self):
        """analyze_video function is still importable."""
        from services.yolo_service import analyze_video
        self.assertTrue(callable(analyze_video))


class TestExistingApiEndpoints(unittest.TestCase):
    """Verify that existing API endpoints still function."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from main import app
        cls.client = TestClient(app)

    def test_home_endpoint(self):
        """Root endpoint returns expected message."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("ForenSight AI Backend Running", res.json()["message"])

    def test_analysis_progress_endpoint(self):
        """Analysis progress endpoint returns valid JSON."""
        res = self.client.get("/analysis-progress/non-existent-id")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("status", data)
        self.assertEqual(data["progress"], 0)

    def test_db_status_endpoint(self):
        """Database status endpoint responds."""
        res = self.client.get("/db-status")
        self.assertEqual(res.status_code, 200)
        self.assertIn("mongodb_connected", res.json())


class TestFrontendNotModified(unittest.TestCase):
    """Verify that no frontend files have been modified."""

    FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

    def test_frontend_directory_exists(self):
        """Frontend directory still exists."""
        self.assertTrue(self.FRONTEND_DIR.exists())

    def test_no_frontend_files_changed(self):
        """
        All frontend files exist and are readable.
        This is a structural check — actual content verification would
        require baseline hashes stored before implementation.
        """
        expected_files = [
            "index.html",
            "evidence.html",
            "reports.html",
            "cases.html",
            "timeline.html",
            "ai-assistant.html",
        ]
        for fname in expected_files:
            fpath = self.FRONTEND_DIR / fname
            self.assertTrue(
                fpath.exists(),
                f"Frontend file {fname} is missing — it should not have been deleted!"
            )

    def test_css_directory_exists(self):
        """CSS directory is still present."""
        css_dir = self.FRONTEND_DIR / "css"
        self.assertTrue(css_dir.exists())

    def test_js_directory_exists(self):
        """JS directory is still present."""
        js_dir = self.FRONTEND_DIR / "js"
        self.assertTrue(js_dir.exists())


if __name__ == "__main__":
    unittest.main()
