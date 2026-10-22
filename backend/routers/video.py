import asyncio
import io
import json
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from gridfs import GridFSBucket
from gridfs.errors import NoFile
from core.config import RESULT_DIR
from core.database import get_db
from services.case_storage import create_case_record, get_case_collection_name
from services.file_service import save_uploaded_file
from services.yolo_service import analyze_video

router = APIRouter(tags=["Video Processing"])

# In-memory progress tracker for live feedback
analysis_progress: dict[str, dict] = {}


@router.get("/analysis-progress/{analysis_id}")
async def get_analysis_progress(analysis_id: str):
    """Returns the current processing status and percentage for a given analysis_id."""
    return analysis_progress.get(
        analysis_id,
        {"status": "idle", "progress": 0, "message": "No active analysis found"}
    )


@router.get("/download-video/{filename}")
async def download_video(filename: str):
    video_path = RESULT_DIR / filename

    if not video_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Annotated video not found"
        )

    return FileResponse(
        path=str(video_path),
        media_type="application/octet-stream",
        filename=filename
    )


def _iter_gridfs_file(grid_file, chunk_size: int = 1024 * 1024):
    try:
        while chunk := grid_file.read(chunk_size):
            yield chunk
    finally:
        grid_file.close()


def _gridfs_upload(bucket, filename: str, source, metadata: dict):
    return bucket.upload_from_stream(filename, source, metadata=metadata)


def _get_case_artifact_bucket_name(
    db, case_id: str, file_id: str, file_field: str
) -> str:
    analysis = db["analysis_results"].find_one(
        {"case_id": case_id, file_field: file_id},
        {"_id": 0, "gridfs_bucket": 1},
    )
    if analysis and analysis.get("gridfs_bucket"):
        bucket_name = analysis["gridfs_bucket"]
        if bucket_name.startswith("case_") or (
            bucket_name.startswith("case") and bucket_name[4:].isdigit()
        ):
            return bucket_name
        raise HTTPException(
            status_code=500,
            detail="Stored case artifact has an invalid GridFS bucket",
        )

    return get_case_collection_name(db, case_id)


@router.get("/videos/{file_id}")
async def get_stored_video(file_id: str):
    """Stream an uploaded or annotated video saved in MongoDB GridFS."""
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=404, detail="Stored video not found")

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable")

    bucket = GridFSBucket(db)
    try:
        grid_file = bucket.open_download_stream(ObjectId(file_id))
    except NoFile:
        raise HTTPException(status_code=404, detail="Stored video not found")

    metadata = grid_file.metadata or {}
    if metadata.get("kind") != "annotated_video":
        grid_file.close()
        raise HTTPException(status_code=404, detail="Stored video not found")

    return StreamingResponse(
        _iter_gridfs_file(grid_file),
        media_type=metadata.get("content_type", "video/mp4"),
        headers={"Content-Disposition": f'inline; filename="{Path(grid_file.filename).name}"'},
    )


@router.get("/case-videos/{case_id}/{file_id}")
async def get_case_video(case_id: str, file_id: str, download: bool = False):
    """Stream an annotated video stored in a case-specific GridFS bucket."""
    try:
        object_id = ObjectId(file_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Stored case video not found")

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable")

    bucket_name = _get_case_artifact_bucket_name(
        db, case_id, file_id, "annotated_video_file_id"
    )
    try:
        grid_file = GridFSBucket(db, bucket_name=bucket_name).open_download_stream(
            object_id
        )
    except NoFile:
        raise HTTPException(status_code=404, detail="Stored case video not found")

    if (grid_file.metadata or {}).get("kind") != "annotated_video":
        grid_file.close()
        raise HTTPException(status_code=404, detail="Stored case video not found")

    return StreamingResponse(
        _iter_gridfs_file(grid_file),
        media_type="video/mp4",
        headers={
            "Content-Disposition": (
                f'{"attachment" if download else "inline"}; '
                f'filename="{Path(grid_file.filename).name}"'
            )
        },
    )


@router.get("/analysis-files/{file_id}")
async def get_stored_analysis_file(file_id: str):
    """Download the JSON result for an analysis from MongoDB GridFS."""
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=404, detail="Analysis file not found")

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable")

    try:
        grid_file = GridFSBucket(db).open_download_stream(ObjectId(file_id))
    except NoFile:
        raise HTTPException(status_code=404, detail="Analysis file not found")

    metadata = grid_file.metadata or {}
    if metadata.get("kind") != "analysis_result":
        grid_file.close()
        raise HTTPException(status_code=404, detail="Analysis file not found")

    return StreamingResponse(
        _iter_gridfs_file(grid_file),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{Path(grid_file.filename).name}"'
            )
        },
    )


@router.get("/case-analysis-files/{case_id}/{file_id}")
async def get_case_analysis_file(case_id: str, file_id: str):
    """Download analysis JSON stored in a case-specific GridFS bucket."""
    try:
        object_id = ObjectId(file_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Case analysis file not found")

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable")

    bucket_name = _get_case_artifact_bucket_name(
        db, case_id, file_id, "result_file_id"
    )
    try:
        grid_file = GridFSBucket(db, bucket_name=bucket_name).open_download_stream(
            object_id
        )
    except NoFile:
        raise HTTPException(status_code=404, detail="Case analysis file not found")

    if (grid_file.metadata or {}).get("kind") != "analysis_result":
        grid_file.close()
        raise HTTPException(status_code=404, detail="Case analysis file not found")

    return StreamingResponse(
        _iter_gridfs_file(grid_file),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{Path(grid_file.filename).name}"'
            )
        },
    )


@router.get("/case-threat-files/{case_id}/{file_id}")
async def get_case_threat_file(case_id: str, file_id: str):
    """Download threat detections JSON from a case-specific GridFS bucket."""
    try:
        object_id = ObjectId(file_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Case threat file not found")

    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="MongoDB is unavailable")

    bucket_name = _get_case_artifact_bucket_name(
        db, case_id, file_id, "threat_file_id"
    )
    try:
        grid_file = GridFSBucket(db, bucket_name=bucket_name).open_download_stream(
            object_id
        )
    except NoFile:
        raise HTTPException(status_code=404, detail="Case threat file not found")

    if (grid_file.metadata or {}).get("kind") != "threat_detections":
        grid_file.close()
        raise HTTPException(status_code=404, detail="Case threat file not found")

    return StreamingResponse(
        _iter_gridfs_file(grid_file),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{Path(grid_file.filename).name}"'
            )
        },
    )


def _persist_to_mongodb(
    analysis_id: str,
    filename: str,
    result: dict,
    annotated_video_path: Optional[Path] = None,
):
    """
    Create one case per uploaded video and store its three artifacts in that
    case's GridFS bucket. The original upload remains temporary.
    """
    db = get_db()
    if db is None:
        raise RuntimeError("MongoDB is unavailable; analysis results were not saved")

    try:
        now = datetime.now(timezone.utc).isoformat()
        detections = result.get("detections", [])
        case = create_case_record(db, analysis_id=analysis_id)
        case_id = case["case_id"]
        bucket_name = case["storage_collection"]
        bucket = GridFSBucket(db, bucket_name=bucket_name)
        file_metadata = {"analysis_id": analysis_id, "case_id": case_id}

        annotated_video_id = None
        if annotated_video_path is not None:
            annotated_filename = f"{analysis_id}_annotated.mp4"
            with annotated_video_path.open("rb") as annotated_file:
                annotated_video_id = _gridfs_upload(
                    bucket,
                    annotated_filename,
                    annotated_file,
                    {
                        **file_metadata,
                        "kind": "annotated_video",
                        "content_type": "video/mp4",
                    },
                )

        annotated_video_url = (
            f"/case-videos/{case_id}/{annotated_video_id}"
            if annotated_video_id
            else None
        )
        threat_detections = [
            detection for detection in detections if detection.get("is_threat")
        ]

        threat_file_id = _gridfs_upload(
            bucket,
            f"{analysis_id}_threats.json",
            io.BytesIO(
                json.dumps(
                    {
                        "analysis_id": analysis_id,
                        "threat_analysis": result.get("threat_analysis"),
                        "threat_detections": threat_detections,
                        "weapon_detections": result.get("weapon_detections", []),
                        "fire_smoke_detections": result.get("fire_smoke_detections", []),
                        "fire_smoke_events": result.get("fire_smoke_events", []),
                    },
                    allow_nan=False,
                ).encode("utf-8")
            ),
            {
                **file_metadata,
                "kind": "threat_detections",
                "content_type": "application/json",
            },
        )
        threats_file_url = f"/case-threat-files/{case_id}/{threat_file_id}"

        result_file_id = _gridfs_upload(
            bucket,
            f"{analysis_id}_result.json",
            io.BytesIO(
                json.dumps(
                    {
                        **result,
                        "case_id": case_id,
                        "case_collection": bucket_name,
                        "video": annotated_video_url,
                        "threats_file": threats_file_url,
                    },
                    allow_nan=False,
                ).encode("utf-8")
            ),
            {
                **file_metadata,
                "kind": "analysis_result",
                "content_type": "application/json",
            },
        )

        # --------------------------------------------------
        # 1. DETECTION RESULTS (per-detection)
        # --------------------------------------------------
        db["detection_results"].delete_many({"analysis_id": analysis_id})
        if detections:
            dr_docs = []
            for d in detections:
                doc = {
                    "analysis_id": analysis_id,
                    "case_id": case_id,
                    "frame_number": d.get("frame"),
                    "timestamp": d.get("timestamp"),
                    "track_id": d.get("track_id"),
                    "object_class": d.get("object"),
                    "confidence": d.get("confidence"),
                    "bounding_box": d.get("bounding_box"),
                }
                if d.get("object") == "person" and d.get("attributes"):
                    doc["person_attributes"] = d["attributes"]
                elif d.get("object") in ["car", "truck", "bus", "motorcycle"] and d.get("attributes"):
                    doc["vehicle_attributes"] = d["attributes"]
                
                if d.get("is_threat"):
                    doc["threat_info"] = {
                        "is_threat": True,
                        "threat_category": d.get("threat_category", "NONE")
                    }
                dr_docs.append(doc)
            db["detection_results"].insert_many(dr_docs)

        # --------------------------------------------------
        # 2. PERSONS (unique tracked persons)
        # --------------------------------------------------
        db["persons"].delete_many({"analysis_id": analysis_id})
        person_tracks = {}
        for d in detections:
            if d.get("object") != "person":
                continue
            track_id = d.get("track_id")
            if track_id is None:
                continue
            
            ts = d.get("timestamp", 0)
            if track_id not in person_tracks:
                person_tracks[track_id] = {
                    "analysis_id": analysis_id,
                    "case_id": case_id,
                    "track_id": track_id,
                    "first_seen": ts,
                    "last_seen": ts,
                    "detection_count": 1,
                }
                if d.get("attributes"):
                    person_tracks[track_id]["attributes"] = d["attributes"]
            else:
                person_tracks[track_id]["last_seen"] = max(person_tracks[track_id]["last_seen"], ts)
                person_tracks[track_id]["detection_count"] += 1
                if "attributes" not in person_tracks[track_id] and d.get("attributes"):
                    person_tracks[track_id]["attributes"] = d["attributes"]
        
        if person_tracks:
            db["persons"].insert_many(list(person_tracks.values()))

        # --------------------------------------------------
        # 3. EVIDENCE (evidence items)
        # --------------------------------------------------
        db["evidence"].delete_many({"analysis_id": analysis_id})
        if detections:
            ev_docs = []
            for d in detections:
                is_threat = d.get("is_threat", False)
                obj = d.get("object", "Unknown")
                conf = float(d.get("confidence", 0))
                ts = float(d.get("timestamp", 0))
                track_id = d.get("track_id")
                threat_cat = d.get("threat_category", "NONE")
                
                desc = f"{obj.capitalize()} detected at {ts:.2f}s with {conf * 100:.1f}% confidence"
                if track_id is not None:
                    desc += f" (Track #{track_id})"
                if threat_cat and threat_cat != "NONE":
                    desc += f" — {threat_cat.replace('_', ' ').title()}"

                doc = {
                    "analysis_id": analysis_id,
                    "case_id": case_id,
                    "track_id": track_id,
                    "timestamp": ts,
                    "evidence_type": "THREAT" if is_threat else "DETECTION",
                    "description": desc,
                    
                    # Carry through other fields so routers don't break
                    "frame": d.get("frame"),
                    "object": obj,
                    "confidence": conf,
                    "is_threat": is_threat,
                    "threat_category": threat_cat,
                    "attributes": d.get("attributes", ""),
                    "bounding_box": d.get("bounding_box")
                }
                if is_threat:
                    doc["threat_metadata"] = {"category": threat_cat}
                    
                ev_docs.append(doc)
            db["evidence"].insert_many(ev_docs)

        # --------------------------------------------------
        # 4. INVESTIGATIONS
        # --------------------------------------------------
        inv_doc = {
            "analysis_id": analysis_id,
            "case_id": case_id,
            "status": "completed",
            "created_at": now,
            "updated_at": now,
            "original_video": filename,
            "annotated_video_file_id": str(annotated_video_id) if annotated_video_id else None,
            "annotated_video": annotated_video_url,
        }
        db["investigations"].update_one(
            {"analysis_id": analysis_id},
            {"$set": inv_doc},
            upsert=True
        )

        # --------------------------------------------------
        # 5. INVESTIGATION REPORTS
        # --------------------------------------------------
        seen = set()
        timeline = []
        for d in detections:
            track_id = d.get("track_id")
            obj = d.get("object", "Unknown")
            key = f"{track_id}_{obj}"
            if key not in seen:
                seen.add(key)
                timeline.append({
                    "timestamp": d.get("timestamp"),
                    "frame": d.get("frame"),
                    "event": f"{obj.capitalize()} first appeared",
                    "object": obj,
                    "track_id": track_id,
                    "confidence": d.get("confidence"),
                    "is_threat": d.get("is_threat", False),
                    "threat_category": d.get("threat_category", "NONE"),
                    "attributes": d.get("attributes", ""),
                })
        timeline.sort(key=lambda x: x["timestamp"] or 0)

        report_doc = {
            "analysis_id": analysis_id,
            "case_id": case_id,
            "total_detections": result.get("total_detections", len(detections)),
            "threat_summary": result.get("threat_analysis"),
            "object_summary": result.get("object_counts"),
            "fire_smoke_events": result.get("fire_smoke_events", []),
            "timeline": timeline,
            "created_at": now,
        }
        report_res = db["investigation_reports"].update_one(
            {"analysis_id": analysis_id},
            {"$set": report_doc},
            upsert=True
        )

        if not report_res.acknowledged:
            raise RuntimeError(f"MongoDB did not acknowledge report for analysis {analysis_id}")

        result_write = db["analysis_results"].update_one(
            {"analysis_id": analysis_id},
            {
                "$set": {
                    "analysis_id": analysis_id,
                    "case_id": case_id,
                    "created_at": now,
                    "gridfs_bucket": bucket_name,
                    "result_file_id": str(result_file_id),
                    "threat_file_id": str(threat_file_id),
                    "annotated_video_file_id": (
                        str(annotated_video_id) if annotated_video_id else None
                    ),
                    "total_detections": result.get("total_detections", len(detections)),
                    "object_counts": result.get("object_counts", {}),
                    "threat_analysis": result.get("threat_analysis"),
                    "fire_smoke_events": result.get("fire_smoke_events", []),
                    "fire_smoke_detections": result.get("fire_smoke_detections", []),
                }
            },
            upsert=True,
        )
        if not result_write.acknowledged:
            raise RuntimeError(f"MongoDB did not acknowledge result for analysis {analysis_id}")

        db[bucket_name].update_one(
            {"analysis_id": analysis_id},
            {
                "$set": {
                    "case_id": case_id,
                    "case_number": case["case_number"],
                    "analysis_id": analysis_id,
                    "annotated_video_file_id": (
                        str(annotated_video_id) if annotated_video_id else None
                    ),
                    "result_file_id": str(result_file_id),
                    "threat_file_id": str(threat_file_id),
                    "created_at": now,
                }
            },
            upsert=True,
        )

        print(f"[MongoDB] Persisted analysis {analysis_id} and its files.")
        return {
            "case_id": case_id,
            "case_number": case["case_number"],
            "case_collection": bucket_name,
            "annotated_video_file_id": (
                str(annotated_video_id) if annotated_video_id else None
            ),
            "result_file_id": str(result_file_id),
            "threat_file_id": str(threat_file_id),
            "annotated_video_url": annotated_video_url,
        }

    except Exception as e:
        raise RuntimeError(f"Failed to persist analysis {analysis_id} to MongoDB: {e}") from e


@router.post("/analyze-video")
async def analyze_cctv(
    file: UploadFile = File(...),
    analysis_id: Optional[str] = Form(None)
):
    if not analysis_id:
        analysis_id = str(uuid.uuid4())

    analysis_progress[analysis_id] = {
        "status": "processing",
        "progress": 3,
        "message": "Saving uploaded video..."
    }

    def _on_progress(pct: int, msg: str):
        analysis_progress[analysis_id] = {
            "status": "processing",
            "progress": pct,
            "message": msg
        }

    with tempfile.TemporaryDirectory(prefix="forensight-analysis-") as working_dir:
        working_path = Path(working_dir)
        upload_dir = working_path / "uploads"
        result_dir = working_path / "results"
        filename, video_path = await save_uploaded_file(file, upload_dir)

        if get_db() is None:
            analysis_progress[analysis_id] = {
                "status": "error",
                "progress": 0,
                "message": "MongoDB is unavailable; analysis was not saved",
            }
            raise HTTPException(
                status_code=503,
                detail="MongoDB is unavailable; video analysis requires MongoDB",
            )

        try:
            result = await asyncio.to_thread(
                analyze_video,
                str(video_path),
                str(result_dir),
                analysis_id=analysis_id,
                progress_callback=_on_progress
            )
        except Exception as e:
            analysis_progress[analysis_id] = {
                "status": "error",
                "progress": 0,
                "message": f"Processing failed: {str(e)}"
            }
            raise HTTPException(
                status_code=500,
                detail=f"YOLO processing failed: {str(e)}"
            ) from e

        # Mirror output files to RESULT_DIR for direct access and fallback
        import shutil
        try:
            for rf in result_dir.glob(f"{analysis_id}_*"):
                shutil.copy2(rf, RESULT_DIR / rf.name)
        except Exception as copy_err:
            print(f"[ForenSight AI] Notice: Could not mirror to RESULT_DIR: {copy_err}")

        try:
            stored_files = await asyncio.to_thread(
                _persist_to_mongodb,
                result["analysis_id"],
                filename,
                result,
                Path(result["video"]),
            )
        except Exception as e:
            analysis_progress[analysis_id] = {
                "status": "error",
                "progress": 0,
                "message": f"Could not save analysis to MongoDB: {e}",
            }
            raise HTTPException(
                status_code=503,
                detail=f"Analysis completed but could not be saved to MongoDB: {e}",
            ) from e

        analysis_progress[analysis_id] = {
            "status": "completed",
            "progress": 100,
            "message": "Analysis completed successfully"
        }

        return {
            "success": True,
            "message": "CCTV video analyzed successfully",
            "original_video": filename,
            "analysis_id": result["analysis_id"],
            "case_id": stored_files["case_id"],
            "case_name": f"Case {stored_files['case_number']}",
            "case_collection": stored_files["case_collection"],
            "result_file_id": stored_files["result_file_id"],
            "detections_file": (
                f"/case-analysis-files/{stored_files['case_id']}/"
                f"{stored_files['result_file_id']}"
            ),
            "threats_file": (
                f"/case-threat-files/{stored_files['case_id']}/"
                f"{stored_files['threat_file_id']}"
            ),
            "total_detections": result["total_detections"],
            "object_counts": result["object_counts"],
            "threat_analysis": result.get("threat_analysis"),
            "annotated_video": stored_files["annotated_video_url"],
            "download_video": (
                f"{stored_files['annotated_video_url']}?download=true"
                if stored_files["annotated_video_url"]
                else None
            ),
            "detections": result["detections"],
            "weapon_detections": result.get("weapon_detections", []),
            "fire_smoke_detections": result.get("fire_smoke_detections", []),
            "fire_smoke_events": result.get("fire_smoke_events", []),
            "performance_metrics": result.get("performance_metrics")
        }
