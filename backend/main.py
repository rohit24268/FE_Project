from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

import os
import shutil
import uuid

from video_processor import (
    get_video_info,
    extract_frames
)


app = FastAPI(title="ForenSight AI")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


UPLOAD_DIR = "uploads"
FRAME_DIR = "frames"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(FRAME_DIR, exist_ok=True)


@app.get("/")
def home():

    return {
        "message": "ForenSight AI Backend is running"
    }


@app.get("/health")
def health():

    return {
        "status": "healthy"
    }


@app.post("/upload-video")
async def upload_video(
    file: UploadFile = File(...)
):

    video_id = str(uuid.uuid4())

    extension = os.path.splitext(
        file.filename
    )[1]

    filename = video_id + extension

    video_path = os.path.join(
        UPLOAD_DIR,
        filename
    )

    with open(video_path, "wb") as buffer:

        shutil.copyfileobj(
            file.file,
            buffer
        )

    video_info = get_video_info(
        video_path
    )

    if video_info is None:

        return {
            "error": "Unable to read video"
        }

    frame_output_dir = os.path.join(
        FRAME_DIR,
        video_id
    )

    frames = extract_frames(
        video_path,
        frame_output_dir,
        interval=1
    )

    return {

        "message": "Video analyzed successfully",

        "video_id": video_id,

        "filename": file.filename,

        "video_info": video_info,

        "frames_extracted": len(frames)
    }