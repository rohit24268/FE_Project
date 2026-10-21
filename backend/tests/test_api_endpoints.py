import sys
import unittest
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from main import app


class TestApiEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_home(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("ForenSight AI Backend Running", res.json()["message"])

    def test_create_case_with_title(self):
        payload = {
            "title": "Incident #Alpha - Main Gate",
            "investigator": "Officer J. Vance",
            "description": "Suspicious activity detected near perimeter",
            "status": "open"
        }
        res = self.client.post("/cases", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["title"], "Incident #Alpha - Main Gate")
        self.assertEqual(data["case_name"], "Incident #Alpha - Main Gate")
        self.assertTrue(bool(data["case_id"]))

    def test_create_case_with_case_name(self):
        # Frontend sends case_name; ensure backward/forward compatibility
        payload = {
            "case_name": "Incident #Beta - Loading Dock",
            "investigator": "Agent M. Doe",
            "description": "Unauthorized access after hours",
            "status": "open"
        }
        res = self.client.post("/cases", json=payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["title"], "Incident #Beta - Loading Dock")
        self.assertEqual(data["case_name"], "Incident #Beta - Loading Dock")

    def test_link_analysis_route_is_removed(self):
        response = self.client.post(
            "/cases/example-case-id/link-analysis",
            json={"analysis_id": "test-uuid-9999"},
        )
        self.assertEqual(response.status_code, 404)

    def test_analysis_progress_endpoint(self):
        res = self.client.get("/analysis-progress/non-existent-id")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("status", data)
        self.assertEqual(data["progress"], 0)


if __name__ == "__main__":
    unittest.main()
