import json
from pathlib import Path
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from gridfs import GridFSBucket
from gridfs.errors import NoFile
from core.config import RESULT_DIR
from core.database import get_db
from services.case_storage import create_case_record, get_case_collection_name
from schemas.cases import CreateCaseRequest, UpdateCaseRequest

router = APIRouter(tags=["Cases"])

CASES_FILE = RESULT_DIR / "cases.json"


# --------------------------------------------------
# JSON FALLBACK HELPERS (kept for backward compat)
# --------------------------------------------------

def _load_cases_json() -> list:
    if not CASES_FILE.exists():
        return []
    try:
        with open(CASES_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_cases_json(cases: list) -> None:
    with open(CASES_FILE, "w") as f:
        json.dump(cases, f, indent=2)


# --------------------------------------------------
# ENDPOINTS
# --------------------------------------------------

@router.get("/cases")
def list_cases():
    """Return all investigation cases."""
    db = get_db()

    if db is not None:
        try:
            cases = list(
                db["cases"]
                .find({"case_id": {"$exists": True}}, {"_id": 0})
                .sort("created_at", -1)
            )
            case_ids = [case["case_id"] for case in cases]
            if case_ids:
                analysis_counts = {
                    item["_id"]: item["count"]
                    for item in db["analysis_results"].aggregate(
                        [
                            {"$match": {"case_id": {"$in": case_ids}}},
                            {"$group": {"_id": "$case_id", "count": {"$sum": 1}}},
                        ]
                    )
                }
                for case in cases:
                    case["analysis_count"] = analysis_counts.get(case["case_id"], 0)
            return cases
        except Exception as e:
            print(f"[MongoDB] Error listing cases: {e}")

    # JSON fallback
    return _load_cases_json()


@router.post("/cases", status_code=201)
def create_case(payload: CreateCaseRequest):
    """Create a new investigation case."""
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="title cannot be empty")

    db = get_db()

    if db is None:
        raise HTTPException(
            status_code=503,
            detail="MongoDB is unavailable; cases require MongoDB storage",
        )

    requested_name = payload.title.strip()
    duplicate = next(
        (
            case
            for case in db["cases"].find(
                {"case_id": {"$exists": True}},
                {"_id": 0, "title": 1, "case_name": 1},
            )
            if (case.get("title") or case.get("case_name") or "").casefold()
            == requested_name.casefold()
        ),
        None,
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="A case with this name already exists",
        )

    return create_case_record(
        db,
        title=payload.title,
        description=payload.description,
        investigator=payload.investigator,
        status=payload.status,
    )


@router.get("/case-session-options")
def list_case_session_options():
    """List case names and video sessions for name-based UI selection."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable")

    cases = list(db["cases"].find({"case_id": {"$exists": True}}, {"_id": 0}))
    options = []
    for case in cases:
        case_id = case.get("case_id")
        case_name = case.get("title") or case.get("case_name")
        if not case_id or not case_name:
            continue

        sessions = []
        for analysis in db["analysis_results"].find(
            {"case_id": case_id},
            {"_id": 0, "analysis_id": 1, "created_at": 1},
        ):
            investigation = db["investigations"].find_one(
                {"analysis_id": analysis["analysis_id"]},
                {"_id": 0, "original_video": 1},
            )
            sessions.append(
                {
                    "analysis_id": analysis["analysis_id"],
                    "video_name": (
                        investigation.get("original_video")
                        if investigation
                        else None
                    ),
                    "created_at": analysis.get("created_at"),
                }
            )
        options.append({"case_name": case_name, "sessions": sessions})

    return {"cases": options}


@router.get("/cases/{case_id}")
def get_case(case_id: str):
    """Get a single case by ID."""
    db = get_db()

    if db is not None:
        try:
            case = db["cases"].find_one(
                {"case_id": case_id},
                {"_id": 0},
            )
            if case:
                return case
        except Exception as e:
            print(f"[MongoDB] Error getting case: {e}")

    # JSON fallback
    for case in _load_cases_json():
        if case["case_id"] == case_id:
            return case

    raise HTTPException(status_code=404, detail="Case not found")


@router.patch("/cases/{case_id}")
def update_case(case_id: str, payload: UpdateCaseRequest):
    """Update editable case details."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No case details were provided")

    for field, value in updates.items():
        if value is None:
            raise HTTPException(
                status_code=400,
                detail=f"{field} cannot be null",
            )
        updates[field] = value.strip()

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db["cases"].update_one(
        {"case_id": case_id},
        {"$set": updates},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Case not found")

    return db["cases"].find_one({"case_id": case_id}, {"_id": 0})


@router.get("/cases/{case_id}/details")
def get_case_details(case_id: str):
    """Return case metadata together with persisted analysis summaries."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable")

    case = db["cases"].find_one(
        {"case_id": case_id},
        {"_id": 0},
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    analyses = list(
        db["analysis_results"].find(
            {"case_id": case_id},
            {
                "_id": 0,
                "analysis_id": 1,
                "created_at": 1,
                "gridfs_bucket": 1,
                "annotated_video_file_id": 1,
                "result_file_id": 1,
                "threat_file_id": 1,
                "total_detections": 1,
                "object_counts": 1,
                "threat_analysis": 1,
            },
        )
    )
    analyses.sort(key=lambda analysis: analysis.get("created_at", ""), reverse=True)

    for analysis in analyses:
        investigation = db["investigations"].find_one(
            {"analysis_id": analysis["analysis_id"]},
            {"_id": 0, "original_video": 1},
        )
        analysis["video_name"] = (
            investigation.get("original_video") if investigation else None
        )
        analysis["annotated_video_url"] = (
            f"/case-videos/{case_id}/{analysis['annotated_video_file_id']}"
            if analysis.get("annotated_video_file_id")
            else None
        )
        analysis["result_url"] = (
            f"/case-analysis-files/{case_id}/{analysis['result_file_id']}"
            if analysis.get("result_file_id")
            else None
        )
        analysis["threats_url"] = (
            f"/case-threat-files/{case_id}/{analysis['threat_file_id']}"
            if analysis.get("threat_file_id")
            else None
        )

    return {"case": case, "analyses": analyses}


@router.get("/cases/by-analysis/{analysis_id}")
def get_case_name_by_analysis(analysis_id: str):
    """Return only the linked case name for an analysis session."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable")

    analysis = db["analysis_results"].find_one(
        {"analysis_id": analysis_id},
        {"_id": 0, "case_id": 1},
    )
    if analysis is None or not analysis.get("case_id"):
        raise HTTPException(
            status_code=404,
            detail="No case found for this analysis session",
        )

    case = db["cases"].find_one(
        {"case_id": analysis["case_id"]},
        {"_id": 0, "title": 1, "case_name": 1, "case_number": 1},
    )
    if case is None:
        raise HTTPException(status_code=404, detail="Linked case not found")

    case_name = (
        case.get("title")
        or case.get("case_name")
        or f"Case {case.get('case_number')}"
    )
    return {"case_name": case_name}


@router.delete("/cases/{case_id}")
def delete_case(case_id: str):
    """Delete a case and its associated records and GridFS artifacts."""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable")

    case = db["cases"].find_one({"case_id": case_id})
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    try:
        analyses = list(db["analysis_results"].find({"case_id": case_id}))
        analysis_ids = {
            analysis["analysis_id"]
            for analysis in analyses
            if analysis.get("analysis_id")
        }
        analysis_ids.update(case.get("analysis_ids", []))

        bucket_names = {
            get_case_collection_name(db, case_id),
            *(
                analysis["gridfs_bucket"]
                for analysis in analyses
                if analysis.get("gridfs_bucket")
            ),
        }
        for bucket_name in bucket_names:
            if not (
                bucket_name.startswith("case_")
                or (
                    bucket_name.startswith("case")
                    and bucket_name[4:].isdigit()
                )
            ):
                raise RuntimeError("Case has an invalid GridFS bucket name")

            files = {}
            file_collection = db[f"{bucket_name}.files"]
            file_queries = [{"metadata.case_id": case_id}]
            if analysis_ids:
                file_queries.append(
                    {"metadata.analysis_id": {"$in": list(analysis_ids)}}
                )
            for query in file_queries:
                for grid_file in file_collection.find(query, {"_id": 1}):
                    files[str(grid_file["_id"])] = grid_file["_id"]

            for analysis in analyses:
                if analysis.get("gridfs_bucket") != bucket_name:
                    continue
                for field in (
                    "annotated_video_file_id",
                    "result_file_id",
                    "threat_file_id",
                ):
                    file_id = analysis.get(field)
                    if file_id and ObjectId.is_valid(file_id):
                        files[file_id] = ObjectId(file_id)

            bucket = GridFSBucket(db, bucket_name=bucket_name)
            for file_id in files.values():
                try:
                    bucket.delete(file_id)
                except NoFile:
                    pass

            db[bucket_name].delete_many({"case_id": case_id})

        related_collections = (
            "analysis_results",
            "detection_results",
            "evidence",
            "persons",
            "investigations",
            "investigation_reports",
        )
        for collection_name in related_collections:
            collection = db[collection_name]
            collection.delete_many({"case_id": case_id})
            for analysis_id in analysis_ids:
                collection.delete_many({"analysis_id": analysis_id})

        db["cases"].delete_one({"case_id": case_id})

        for bucket_name in bucket_names:
            other_case_uses_bucket = (
                db["cases"].find_one({"storage_collection": bucket_name})
                is not None
            )
            other_analysis_uses_bucket = (
                db["analysis_results"].find_one({"gridfs_bucket": bucket_name})
                is not None
            )
            if not other_case_uses_bucket and not other_analysis_uses_bucket:
                db.drop_collection(bucket_name)
                db.drop_collection(f"{bucket_name}.files")
                db.drop_collection(f"{bucket_name}.chunks")

        cases = _load_cases_json()
        remaining_cases = [
            item for item in cases if item.get("case_id") != case_id
        ]
        if len(remaining_cases) != len(cases):
            _save_cases_json(remaining_cases)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete case and associated data: {error}",
        ) from error

    return {"success": True, "case_id": case_id}


@router.patch("/cases/{case_id}/status")
def update_case_status(case_id: str, status: str):
    """Update the status of a case (open / pending / closed)."""
    allowed = {"open", "pending", "closed"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"status must be one of {allowed}")

    db = get_db()

    if db is not None:
        try:
            result = db["cases"].find_one_and_update(
                {"case_id": case_id},
                {"$set": {"status": status}},
                return_document=True,
                projection={"_id": 0},
            )
            if result:
                # Dual-write to JSON
                cases = _load_cases_json()
                for c in cases:
                    if c["case_id"] == case_id:
                        c["status"] = status
                        break
                _save_cases_json(cases)
                return result
        except Exception as e:
            print(f"[MongoDB] Error updating status: {e}")

    # JSON fallback
    cases = _load_cases_json()
    for case in cases:
        if case["case_id"] == case_id:
            case["status"] = status
            _save_cases_json(cases)
            return case

    raise HTTPException(status_code=404, detail="Case not found")
