import json
import io
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from fastapi.testclient import TestClient
from routers.cases import create_case, get_case_details
from routers.evidence import get_evidence
from schemas.cases import CreateCaseRequest
from routers.video import _persist_to_mongodb
from main import app
from services.case_storage import get_case_collection_name


class FakeCursor(list):
    def sort(self, key_or_list, direction=None):
        if isinstance(key_or_list, str):
            super().sort(
                key=lambda document: document.get(key_or_list),
                reverse=direction == -1,
            )
        return self


class FakeCollection:
    def __init__(self):
        self.documents = []
        self.updates = []

    def delete_many(self, query):
        self.documents = [
            document
            for document in self.documents
            if not self._matches(document, query)
        ]

    def delete_one(self, query):
        for index, document in enumerate(self.documents):
            if self._matches(document, query):
                del self.documents[index]
                break

    def insert_many(self, documents):
        self.documents.extend(documents)

    def insert_one(self, document):
        self.documents.append(document)

    def find(self, query, projection=None):
        def matches(document, key, value):
            actual = document
            for part in key.split("."):
                if not isinstance(actual, dict) or part not in actual:
                    return False
                actual = actual[part]
            if isinstance(value, dict) and "$exists" in value:
                return (actual is not None) == value["$exists"]
            if isinstance(value, dict) and "$in" in value:
                return actual in value["$in"]
            return actual == value

        documents = [
            document
            for document in self.documents
            if all(matches(document, key, value) for key, value in query.items())
        ]
        return FakeCursor(documents)

    def _matches(self, document, query):
        return any(item is document for item in self.find(query))

    def find_one(self, query, projection=None):
        return next(iter(self.find(query, projection)), None)

    def find_one_and_update(self, query, update, **_kwargs):
        document = self.find_one(query)
        if document is None and _kwargs.get("upsert"):
            document = dict(query)
            self.documents.append(document)
        if document:
            for key, value in update.get("$inc", {}).items():
                document[key] = document.get(key, 0) + value
            for key, value in update.get("$addToSet", {}).items():
                document.setdefault(key, [])
                if value not in document[key]:
                    document[key].append(value)
        return document

    def update_many(self, _query, _update):
        return type("WriteResult", (), {"acknowledged": True})()

    def update_one(self, query, update, upsert=False):
        self.updates.append((query, update, upsert))
        document = self.find_one(query)
        matched_count = 1 if document else 0
        if document is None and upsert:
            document = dict(query)
            self.documents.append(document)
        if document:
            document.update(update.get("$set", {}))
        return type(
            "WriteResult",
            (),
            {"acknowledged": True, "matched_count": matched_count},
        )()


class FakeDatabase:
    def __init__(self):
        self.collections = {}
        self.gridfs = {}

    def create_collection(self, name):
        if name in self.collections:
            raise ValueError("collection already exists")
        return self.collections.setdefault(name, FakeCollection())

    def drop_collection(self, name):
        self.collections.pop(name, None)

    def __getitem__(self, name):
        return self.collections.setdefault(name, FakeCollection())


class FakeGridFSBucket:
    def __init__(self, database, bucket_name="fs"):
        self.files = database.gridfs.setdefault(bucket_name, {})

    def upload_from_stream(self, filename, source, metadata):
        from bson import ObjectId

        file_id = ObjectId()
        self.files[str(file_id)] = {
            "filename": filename,
            "content": source.read(),
            "metadata": metadata,
        }
        return file_id

    def open_download_stream(self, file_id):
        from bson import ObjectId

        file = self.files.get(str(file_id))
        if file is None:
            from gridfs.errors import NoFile

            raise NoFile(file_id)

        result = io.BytesIO(file["content"])
        result.filename = file["filename"]
        result.metadata = file["metadata"]
        return result

    def delete(self, file_id):
        self.files.pop(str(file_id), None)


class TestVideoPersistence(unittest.TestCase):
    def test_case_can_update_description_and_assign_investigator(self):
        database = FakeDatabase()
        case_id = str(uuid.uuid4())
        case = {
            "case_id": case_id,
            "title": "Solo",
            "description": "Old description",
            "investigator": "",
        }
        database["cases"].documents.append(case)

        with patch("routers.cases.get_db", return_value=database), TestClient(app) as client:
            response = client.patch(
                f"/cases/{case_id}",
                json={
                    "description": "Updated description",
                    "investigator": "Jordan Lee",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["description"], "Updated description")
        self.assertEqual(response.json()["investigator"], "Jordan Lee")

    def test_case_update_rejects_unknown_case(self):
        database = FakeDatabase()
        with patch("routers.cases.get_db", return_value=database), TestClient(app) as client:
            response = client.patch(
                f"/cases/{uuid.uuid4()}",
                json={"investigator": "Jordan Lee"},
            )

        self.assertEqual(response.status_code, 404, response.text)
    def test_case_session_options_include_case_and_video_names(self):
        database = FakeDatabase()
        case_id = str(uuid.uuid4())
        database["cases"].documents.append(
            {"case_id": case_id, "title": "Solo", "case_name": "Solo"}
        )
        database["analysis_results"].documents.append(
            {
                "analysis_id": "internal-session-id",
                "case_id": case_id,
                "created_at": "2026-10-21T09:41:44+00:00",
            }
        )
        database["investigations"].documents.append(
            {
                "analysis_id": "internal-session-id",
                "original_video": "camera.mp4",
            }
        )

        with (
            patch("routers.cases.get_db", return_value=database),
            TestClient(app) as client,
        ):
            response = client.get("/case-session-options")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["cases"][0]["case_name"], "Solo")
        self.assertEqual(
            response.json()["cases"][0]["sessions"][0]["video_name"],
            "camera.mp4",
        )

    def test_case_names_must_be_unique(self):
        database = FakeDatabase()
        database["cases"].documents.append(
            {
                "case_id": str(uuid.uuid4()),
                "title": "Solo",
                "case_name": "Solo",
            }
        )

        with (
            patch("routers.cases.get_db", return_value=database),
            TestClient(app) as client,
        ):
            response = client.post("/cases", json={"title": "solo"})

        self.assertEqual(response.status_code, 409, response.text)

    def test_evidence_response_includes_linked_case_name_only(self):
        database = FakeDatabase()
        case_id = str(uuid.uuid4())
        analysis_id = "analysis-session-123"
        database["cases"].documents.append(
            {
                "case_id": case_id,
                "title": "Solo",
                "case_name": "Solo",
            }
        )
        database["analysis_results"].documents.append(
            {
                "analysis_id": analysis_id,
                "case_id": case_id,
                "annotated_video_file_id": "annotated-video-file",
            }
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            detections_path = Path(temp_dir) / f"{analysis_id}_detections.json"
            detections_path.write_text(
                json.dumps(
                    [
                        {
                            "object": "person",
                            "confidence": 0.9,
                            "timestamp": 1.0,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            with (
                patch("routers.evidence.get_db", return_value=database),
                patch("routers.evidence.RESULT_DIR", Path(temp_dir)),
                patch("routers.evidence._load_threat_data", return_value=None),
            ):
                result = get_evidence(analysis_id)

        self.assertEqual(result["case_name"], "Solo")
        self.assertEqual(
            result["annotated_video_url"],
            f"/case-videos/{case_id}/annotated-video-file",
        )
        self.assertNotIn("case_id", result)

    def test_analysis_session_lookup_returns_only_case_name(self):
        database = FakeDatabase()
        case_id = str(uuid.uuid4())
        analysis_id = "analysis-session-lookup"
        database["analysis_results"].documents.append(
            {"analysis_id": analysis_id, "case_id": case_id}
        )
        database["cases"].documents.append(
            {"case_id": case_id, "title": "Solo", "case_name": "Solo"}
        )

        with (
            patch("routers.cases.get_db", return_value=database),
            TestClient(app) as client,
        ):
            response = client.get(f"/cases/by-analysis/{analysis_id}")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"case_name": "Solo"})

    def test_case_details_include_analysis_summaries_and_artifact_urls(self):
        database = FakeDatabase()
        case_id = str(uuid.uuid4())
        database["cases"].documents.append(
            {
                "case_id": case_id,
                "case_number": 1,
                "storage_collection": "case1",
                "title": "Case 1",
            }
        )
        database["analysis_results"].documents.append(
            {
                "analysis_id": "analysis-123",
                "case_id": case_id,
                "created_at": "2026-10-21T08:39:29+00:00",
                "annotated_video_file_id": "video-id",
                "result_file_id": "result-id",
                "threat_file_id": "threat-id",
                "total_detections": 4,
                "object_counts": {"person": 4},
                "threat_analysis": {"overall_threat_level": "LOW"},
            }
        )

        with patch("routers.cases.get_db", return_value=database):
            details = get_case_details(case_id)

        self.assertEqual(details["case"]["title"], "Case 1")
        self.assertEqual(len(details["analyses"]), 1)
        analysis = details["analyses"][0]
        self.assertEqual(analysis["total_detections"], 4)
        self.assertEqual(
            analysis["annotated_video_url"],
            f"/case-videos/{case_id}/video-id",
        )
        self.assertEqual(
            analysis["result_url"],
            f"/case-analysis-files/{case_id}/result-id",
        )
        self.assertEqual(
            analysis["threats_url"],
            f"/case-threat-files/{case_id}/threat-id",
        )

    def test_case_artifact_routes_use_the_persisted_gridfs_bucket(self):
        database = FakeDatabase()
        case_id = str(uuid.uuid4())
        database["cases"].documents.append(
            {
                "case_id": case_id,
                "case_number": 2,
                "storage_collection": "case2",
            }
        )
        bucket = FakeGridFSBucket(database, bucket_name="case3")
        video_id = str(
            bucket.upload_from_stream(
                "annotated.mp4",
                io.BytesIO(b"video"),
                {"kind": "annotated_video"},
            )
        )
        result_id = str(
            bucket.upload_from_stream(
                "result.json",
                io.BytesIO(b'{"result":true}'),
                {"kind": "analysis_result"},
            )
        )
        threat_id = str(
            bucket.upload_from_stream(
                "threats.json",
                io.BytesIO(b'{"threats":[]}'),
                {"kind": "threat_detections"},
            )
        )
        database["analysis_results"].documents.append(
            {
                "case_id": case_id,
                "gridfs_bucket": "case3",
                "annotated_video_file_id": video_id,
                "result_file_id": result_id,
                "threat_file_id": threat_id,
            }
        )

        with (
            patch("routers.video.get_db", return_value=database),
            patch("routers.video.GridFSBucket", side_effect=FakeGridFSBucket),
            TestClient(app) as client,
        ):
            video_response = client.get(f"/case-videos/{case_id}/{video_id}")
            result_response = client.get(
                f"/case-analysis-files/{case_id}/{result_id}"
            )
            threats_response = client.get(
                f"/case-threat-files/{case_id}/{threat_id}"
            )

        self.assertEqual(video_response.status_code, 200, video_response.text)
        self.assertEqual(video_response.content, b"video")
        self.assertEqual(result_response.status_code, 200, result_response.text)
        self.assertEqual(result_response.content, b'{"result":true}')
        self.assertEqual(threats_response.status_code, 200, threats_response.text)
        self.assertEqual(threats_response.content, b'{"threats":[]}')

    def test_delete_case_removes_linked_records_and_gridfs_files(self):
        database = FakeDatabase()
        case_id = str(uuid.uuid4())
        other_case_id = str(uuid.uuid4())
        database["cases"].documents.extend(
            [
                {
                    "case_id": case_id,
                    "case_number": 2,
                    "storage_collection": "case2",
                    "analysis_ids": ["analysis-123"],
                },
                {
                    "case_id": other_case_id,
                    "case_number": 3,
                    "storage_collection": "case3",
                    "analysis_ids": ["analysis-other"],
                },
            ]
        )
        bucket = FakeGridFSBucket(database, bucket_name="case3")
        database["case2"].documents.append(
            {"analysis_id": "orphaned-analysis-without-case-id"}
        )
        video_id = bucket.upload_from_stream(
            "annotated.mp4",
            io.BytesIO(b"video"),
            {"kind": "annotated_video", "case_id": case_id},
        )
        database["analysis_results"].documents.extend(
            [
                {
                    "case_id": case_id,
                    "analysis_id": "analysis-123",
                    "gridfs_bucket": "case3",
                    "annotated_video_file_id": str(video_id),
                },
                {
                    "case_id": other_case_id,
                    "analysis_id": "analysis-other",
                    "gridfs_bucket": "case3",
                },
            ]
        )
        database["evidence"].documents.extend(
            [
                {"case_id": case_id, "analysis_id": "analysis-123"},
                {"case_id": other_case_id, "analysis_id": "analysis-other"},
            ]
        )

        with (
            patch("routers.cases.get_db", return_value=database),
            patch("routers.cases.GridFSBucket", side_effect=FakeGridFSBucket),
            TestClient(app) as client,
        ):
            response = client.delete(f"/cases/{case_id}")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"success": True, "case_id": case_id})
        self.assertIsNone(database["cases"].find_one({"case_id": case_id}))
        self.assertIsNotNone(database["cases"].find_one({"case_id": other_case_id}))
        self.assertIsNone(
            database["analysis_results"].find_one({"case_id": case_id})
        )
        self.assertIsNotNone(
            database["analysis_results"].find_one({"case_id": other_case_id})
        )
        self.assertFalse(database.gridfs["case3"])
        self.assertEqual(len(database["evidence"].documents), 1)
        self.assertEqual(database["evidence"].documents[0]["case_id"], other_case_id)
        self.assertNotIn("case2", database.collections)
        self.assertNotIn("case2.files", database.collections)
        self.assertNotIn("case2.chunks", database.collections)
        self.assertIn("case3", database.collections)

    def test_case_creation_makes_case_specific_collection(self):
        database = FakeDatabase()
        with patch("routers.cases.get_db", return_value=database):
            case = create_case(CreateCaseRequest(title="Case-specific storage"))

        collection_name = get_case_collection_name(database, case["case_id"])
        self.assertEqual(collection_name, "case1")
        self.assertEqual(case["case_name"], "Case-specific storage")
        self.assertEqual(case["storage_collection"], collection_name)
        self.assertIn(collection_name, database.collections)
        self.assertTrue(
            any(
                document.get("case_id") == case["case_id"]
                for document in database["cases"].documents
            )
        )
        with patch("routers.cases.get_db", return_value=database):
            second_case = create_case(CreateCaseRequest(title="Second case"))
        self.assertEqual(
            get_case_collection_name(database, second_case["case_id"]),
            "case2",
        )

    def test_saves_only_annotated_video_and_full_result(self):
        database = FakeDatabase()
        result = {
            "analysis_id": "analysis-123",
            "video": "annotated.mp4",
            "total_detections": 1,
            "object_counts": {"person": 1},
            "threat_analysis": {"overall_threat_level": "SAFE"},
            "detections": [
                {
                    "frame": 1,
                    "timestamp": 0.1,
                    "object": "person",
                    "confidence": 0.9,
                    "track_id": 1,
                    "is_threat": True,
                    "threat_category": "LETHAL_WEAPON",
                }
            ],
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            annotated_path = Path(temp_dir) / "annotated.mp4"
            annotated_path.write_bytes(b"annotated-video")

            with patch("routers.video.get_db", return_value=database), patch(
                "routers.video.GridFSBucket", side_effect=FakeGridFSBucket
            ):
                file_ids = _persist_to_mongodb(
                    "analysis-123",
                    "original.mp4",
                    result,
                    annotated_video_path=annotated_path,
                )

        bucket = database.gridfs[file_ids["case_collection"]]
        self.assertEqual(len(bucket), 3)
        self.assertEqual(
            bucket[file_ids["annotated_video_file_id"]]["content"],
            b"annotated-video",
        )
        saved_result = json.loads(bucket[file_ids["result_file_id"]]["content"])
        self.assertEqual(
            saved_result["video"],
            file_ids["annotated_video_url"],
        )
        self.assertEqual(saved_result["detections"], result["detections"])
        threat_json = json.loads(bucket[file_ids["threat_file_id"]]["content"])
        self.assertEqual(len(threat_json["threat_detections"]), 1)
        self.assertEqual(
            threat_json["threat_detections"][0]["threat_category"],
            "LETHAL_WEAPON",
        )
        self.assertEqual(file_ids["case_collection"], "case1")

        analysis_update = database["analysis_results"].updates[0][1]["$set"]
        self.assertEqual(analysis_update["result_file_id"], file_ids["result_file_id"])
        self.assertEqual(
            analysis_update["annotated_video_file_id"],
            file_ids["annotated_video_file_id"],
        )

    def test_requires_mongodb(self):
        with patch("routers.video.get_db", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "MongoDB is unavailable"):
                _persist_to_mongodb("analysis-123", "original.mp4", {})

    def test_analysis_removes_local_working_files(self):
        working_directories = []

        async def fake_save_upload(upload, upload_dir):
            upload_dir.mkdir(parents=True)
            video_path = upload_dir / "upload.mp4"
            video_path.write_bytes(await upload.read())
            working_directories.append(upload_dir.parent)
            return "upload.mp4", video_path

        def fake_analyze_video(video_path, result_dir, analysis_id, progress_callback):
            result_path = Path(result_dir)
            result_path.mkdir(parents=True)
            annotated_path = result_path / f"{analysis_id}_annotated.mp4"
            annotated_path.write_bytes(b"annotated")
            return {
                "analysis_id": analysis_id,
                "video": str(annotated_path),
                "total_detections": 0,
                "object_counts": {},
                "threat_analysis": {},
                "detections": [],
            }

        with (
            patch("routers.video.get_db", return_value=object()),
            patch("routers.video.save_uploaded_file", side_effect=fake_save_upload),
            patch("routers.video.analyze_video", side_effect=fake_analyze_video),
            patch(
                "routers.video._persist_to_mongodb",
                return_value={
                    "case_id": str(uuid.uuid4()),
                    "case_number": 1,
                    "case_collection": "case1",
                    "annotated_video_file_id": "annotated-id",
                    "result_file_id": "result-id",
                    "threat_file_id": "threat-id",
                    "annotated_video_url": "/case-videos/example/annotated-id",
                },
            ),
            TestClient(app) as client,
        ):
            response = client.post(
                "/analyze-video",
                files={"file": ("camera.mp4", b"uploaded", "video/mp4")},
                data={"analysis_id": "temporary-analysis"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(working_directories), 1)
        self.assertFalse(working_directories[0].exists())


if __name__ == "__main__":
    unittest.main()
