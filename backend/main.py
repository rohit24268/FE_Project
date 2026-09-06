from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from pathlib import Path
import shutil
import uuid
import os

from services.yolo_service import analyze_video
from fastapi.responses import FileResponse


# --------------------------------------------------
# FASTAPI APP
# --------------------------------------------------

app = FastAPI(
    title="ForenSight AI",
    description="AI-powered CCTV forensic analysis system",
    version="1.0.0"
)


# --------------------------------------------------
# CORS
# --------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# DIRECTORIES
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_DIR = BASE_DIR / "uploads"
RESULT_DIR = BASE_DIR / "results"

UPLOAD_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)


# --------------------------------------------------
# SERVE PROCESSED RESULTS
# --------------------------------------------------

app.mount(
    "/results",
    StaticFiles(directory=str(RESULT_DIR)),
    name="results"
)


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.get("/")
def home():

    return {
        "message": "ForenSight AI Backend Running"
    }

@app.get("/download-video/{filename}")
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

# --------------------------------------------------
# ANALYZE CCTV VIDEO
# --------------------------------------------------

@app.post("/analyze-video")
async def analyze_cctv(
    file: UploadFile = File(...)
):

    # --------------------------------------------------
    # CHECK FILE
    # --------------------------------------------------

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No video file provided"
        )

    allowed_extensions = {
        ".mp4",
        ".avi",
        ".mov",
        ".mkv",
        ".webm"
    }

    file_extension = Path(
        file.filename
    ).suffix.lower()

    if file_extension not in allowed_extensions:

        raise HTTPException(
            status_code=400,
            detail="Unsupported video format"
        )


    # --------------------------------------------------
    # CREATE UNIQUE FILE NAME
    # --------------------------------------------------

    video_id = str(uuid.uuid4())

    filename = f"{video_id}{file_extension}"

    video_path = UPLOAD_DIR / filename


    # --------------------------------------------------
    # SAVE UPLOADED VIDEO
    # --------------------------------------------------

    try:

        with open(video_path, "wb") as buffer:

            shutil.copyfileobj(
                file.file,
                buffer
            )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=f"Failed to save video: {str(e)}"
        )

    finally:

        await file.close()


    # --------------------------------------------------
    # RUN YOLO ANALYSIS
    # --------------------------------------------------

    try:

        result = analyze_video(
            str(video_path),
            str(RESULT_DIR)
        )

    except Exception as e:

        # Remove uploaded video if processing fails
        if video_path.exists():

            try:
                os.remove(video_path)
            except Exception:
                pass

        raise HTTPException(
            status_code=500,
            detail=f"YOLO processing failed: {str(e)}"
        )


    # --------------------------------------------------
    # REMOVE ORIGINAL UPLOAD
    # --------------------------------------------------

    try:

        if video_path.exists():
            os.remove(video_path)

    except Exception:
        pass


    # --------------------------------------------------
    # RETURN ANALYSIS RESULTS
    # --------------------------------------------------

    return {

        "success": True,

        "message":
            "CCTV video analyzed successfully",

        "original_video":
            filename,

        "analysis_id":
            result["analysis_id"],

        "total_detections":
            result["total_detections"],

        "object_counts":
            result["object_counts"],

        "annotated_video":
            (
                f"/results/"
                f"{result['analysis_id']}"
                f"_annotated.mp4"
            ),

        "detections_file":
            (
                f"/results/"
                f"{result['analysis_id']}"
                f"_detections.json"
            ),

        "detections":
            result["detections"]
    }