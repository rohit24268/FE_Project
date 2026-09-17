import unittest
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from services.ai_investigator import build_case_context, SYSTEM_PROMPT


class TestInvestigatorThreat(unittest.TestCase):

    def test_system_prompt_threat_role(self):
        self.assertIn("Threat & Incident Response AI Forensic Analyst", SYSTEM_PROMPT)
        self.assertIn("Threat Assessment Summary", SYSTEM_PROMPT)

    def test_build_case_context_with_threat_data(self):
        detections = [
            {
                "frame": 10,
                "timestamp": 1.0,
                "object": "person",
                "confidence": 0.92,
                "track_id": 1,
                "bounding_box": {"x1": 50, "y1": 50, "x2": 150, "y2": 250},
                "attributes": "Person in dark jacket",
            },
            {
                "frame": 10,
                "timestamp": 1.0,
                "object": "knife",
                "confidence": 0.88,
                "track_id": 2,
                "bounding_box": {"x1": 60, "y1": 120, "x2": 90, "y2": 160},
                "is_threat": True,
                "threat_category": "LETHAL_WEAPON",
            }
        ]

        threat_analysis = {
            "max_threat_score": 0.89,
            "overall_threat_level": "CRITICAL",
            "total_incidents": 1,
            "incidents": [
                {
                    "start_time": 1.0,
                    "end_time": 2.5,
                    "duration": 1.5,
                    "peak_score": 0.89,
                    "peak_level": "CRITICAL",
                    "threat_types": ["knife"],
                    "categories": ["LETHAL_WEAPON"],
                    "armed_person": True,
                }
            ],
            "threat_summary": {
                "threat_objects_seen": {"knife": 15}
            }
        }

        context = build_case_context(detections, threat_analysis=threat_analysis)

        self.assertIn("=== THREAT ASSESSMENT SUMMARY ===", context)
        self.assertIn("Overall Threat Level: CRITICAL", context)
        self.assertIn("Peak Threat Risk Score: 0.89", context)
        self.assertIn("=== INCIDENT TIMELINE ===", context)
        self.assertIn("Armed Suspect: YES", context)
        self.assertIn("knife", context)
        self.assertIn("Person in dark jacket", context)

    def test_build_case_context_computes_threats_if_none(self):
        detections = [
            {
                "frame": 5,
                "timestamp": 0.5,
                "object": "person",
                "confidence": 0.9,
                "track_id": 1,
                "bounding_box": {"x1": 100, "y1": 100, "x2": 200, "y2": 300},
            }
        ]
        context = build_case_context(detections, threat_analysis=None)
        self.assertIn("=== THREAT ASSESSMENT SUMMARY ===", context)
        self.assertIn("Overall Threat Level: SAFE", context)


if __name__ == "__main__":
    unittest.main()
