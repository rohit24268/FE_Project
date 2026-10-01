from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from core.config import RESULT_DIR
from core.database import get_db
from services.file_service import save_uploaded_file, remove_file
from services.yolo_service import analyze_video

router = APIRouter(tags=["Video Processing"])


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


def _persist_to_mongodb(analysis_id: str, filename: str, result: dict):
    """
    Persist analysis results to MongoDB across 6 distinct collections.
    Called AFTER successful YOLO analysis.
    """
    db = get_db()
    if db is None:
        return

    try:
        now = datetime.now(timezone.utc).isoformat()
        detections = result.get("detections", [])

        # --------------------------------------------------
        # 1. DETECTION RESULTS (per-detection)
        # --------------------------------------------------
        db["detection_results"].delete_many({"analysis_id": analysis_id})
        if detections:
            dr_docs = []
            for d in detections:
                doc = {
                    "analysis_id": analysis_id,
                    "case_id": None,
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
                    "case_id": None,
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
                    "case_id": None,
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
            "case_id": None,
            "status": "completed",
            "created_at": now,
            "updated_at": now,
            "original_video": filename,
            "annotated_video": f"/results/{analysis_id}_annotated.mp4",
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
            "case_id": None,
            "total_detections": result.get("total_detections", len(detections)),
            "threat_summary": result.get("threat_analysis"),
            "object_summary": result.get("object_counts"),
            "timeline": timeline,
            "created_at": now,
        }
        report_res = db["investigation_reports"].update_one(
            {"analysis_id": analysis_id},
            {"$set": report_doc},
            upsert=True
        )

        if report_res.acknowledged:
            print(f"[MongoDB] Persisted analysis {analysis_id} across 5 collections.")
        else:
            print(f"[MongoDB] WARNING: Write unacknowledged for analysis {analysis_id}")

    except Exception as e:
        print(f"[MongoDB] WARNING: Failed to persist analysis data — {e}")


@router.post("/analyze-video")
async def analyze_cctv(
    file: UploadFile = File(...)
):
    filename, video_path = await save_uploaded_file(file)

    try:
        result = analyze_video(
            str(video_path),
            str(RESULT_DIR)
        )
    except Exception as e:
        remove_file(video_path)
        raise HTTPException(
            status_code=500,
            detail=f"YOLO processing failed: {str(e)}"
        )

    remove_file(video_path)

    # --------------------------------------------------
    # PERSIST TO MONGODB (after successful YOLO analysis)
    # --------------------------------------------------
    _persist_to_mongodb(result["analysis_id"], filename, result)

    return {
        "success": True,
        "message": "CCTV video analyzed successfully",
        "original_video": filename,
        "analysis_id": result["analysis_id"],
        "total_detections": result["total_detections"],
        "object_counts": result["object_counts"],
        "threat_analysis": result.get("threat_analysis"),
        "annotated_video": f"/results/{result['analysis_id']}_annotated.mp4",
        "detections_file": f"/results/{result['analysis_id']}_detections.json",
        "threats_file": f"/results/{result['analysis_id']}_threats.json",
        "detections": result["detections"]
    }
