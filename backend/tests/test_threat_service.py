import sys
import unittest
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from services.threat_service import (
    get_base_threat_weight,
    is_in_proximity,
    score_frame_threat,
    analyze_video_threats,
)


class TestThreatService(unittest.TestCase):

    def test_get_base_threat_weight(self):
        weight, cat = get_base_threat_weight("knife")
        self.assertEqual(cat, "LETHAL_WEAPON")
        self.assertGreaterEqual(weight, 0.70)

        weight, cat = get_base_threat_weight("pistol")
        self.assertEqual(cat, "LETHAL_WEAPON")
        self.assertGreaterEqual(weight, 0.80)

        weight, cat = get_base_threat_weight("baseball bat")
        self.assertEqual(cat, "BLUNT_WEAPON")
        self.assertGreaterEqual(weight, 0.50)

        weight, cat = get_base_threat_weight("car")
        self.assertEqual(cat, "NONE")
        self.assertEqual(weight, 0.0)

    def test_proximity_calculation(self):
        person_box = {"x1": 100, "y1": 100, "x2": 200, "y2": 300}
        # Weapon overlapping with person
        weapon_box_overlap = {"x1": 120, "y1": 180, "x2": 150, "y2": 210}
        self.assertTrue(is_in_proximity(weapon_box_overlap, person_box))

        # Weapon completely far away
        weapon_box_far = {"x1": 600, "y1": 500, "x2": 650, "y2": 550}
        self.assertFalse(is_in_proximity(weapon_box_far, person_box))

    def test_score_frame_safe(self):
        detections = [
            {"object": "person", "confidence": 0.90, "bounding_box": {"x1": 100, "y1": 100, "x2": 200, "y2": 300}},
            {"object": "car", "confidence": 0.85, "bounding_box": {"x1": 300, "y1": 200, "x2": 500, "y2": 400}},
        ]
        result = score_frame_threat(detections)
        self.assertEqual(result["threat_level"], "SAFE")
        self.assertEqual(result["threat_score"], 0.0)
        self.assertFalse(result["armed_person_detected"])

    def test_score_frame_armed_person(self):
        detections = [
            {"object": "person", "confidence": 0.90, "bounding_box": {"x1": 100, "y1": 100, "x2": 200, "y2": 300}},
            {"object": "knife", "confidence": 0.85, "bounding_box": {"x1": 110, "y1": 190, "x2": 140, "y2": 220}},
        ]
        result = score_frame_threat(detections)
        self.assertIn(result["threat_level"], ("HIGH", "CRITICAL"))
        self.assertGreaterEqual(result["threat_score"], 0.70)
        self.assertTrue(result["armed_person_detected"])
        self.assertEqual(len(result["threat_objects"]), 1)

    def test_analyze_video_threats_temporal(self):
        detections = []
        # Frame 0 to 10: safe
        for i in range(10):
            detections.append({
                "frame": i,
                "timestamp": i * 0.1,
                "object": "person",
                "confidence": 0.9,
                "bounding_box": {"x1": 100, "y1": 100, "x2": 200, "y2": 300},
            })

        # Frame 11 to 25: knife detected near person (1.4 seconds duration)
        for i in range(11, 26):
            detections.append({
                "frame": i,
                "timestamp": i * 0.1,
                "object": "person",
                "confidence": 0.9,
                "bounding_box": {"x1": 100, "y1": 100, "x2": 200, "y2": 300},
            })
            detections.append({
                "frame": i,
                "timestamp": i * 0.1,
                "object": "knife",
                "confidence": 0.85,
                "bounding_box": {"x1": 110, "y1": 190, "x2": 140, "y2": 220},
            })

        result = analyze_video_threats(detections, min_persistence_seconds=0.5)
        self.assertGreaterEqual(result["max_threat_score"], 0.70)
        self.assertIn(result["overall_threat_level"], ("HIGH", "CRITICAL"))
        self.assertEqual(result["total_incidents"], 1)
        incident = result["incidents"][0]
        self.assertIn("knife", incident["threat_types"])
        self.assertTrue(incident["armed_person"])
        self.assertGreaterEqual(incident["duration"], 1.0)


if __name__ == "__main__":
    unittest.main()
