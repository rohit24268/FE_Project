from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from core.config import RESULT_DIR
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

    return {
        "success": True,
        "message": "CCTV video analyzed successfully",
        "original_video": filename,
        "analysis_id": result["analysis_id"],
        "total_detections": result["total_detections"],
        "object_counts": result["object_counts"],
        "annotated_video": f"/results/{result['analysis_id']}_annotated.mp4",
        "detections_file": f"/results/{result['analysis_id']}_detections.json",
        "detections": result["detections"]
    }
