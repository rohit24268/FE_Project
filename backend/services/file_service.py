import os
import shutil
import uuid
from pathlib import Path
from fastapi import UploadFile, HTTPException
from core.config import UPLOAD_DIR


async def save_uploaded_file(
    file: UploadFile,
    upload_dir: Path = UPLOAD_DIR,
) -> tuple[str, Path]:
    """
    Validates and saves an uploaded video file to the selected directory.
    Returns (filename, video_path).
    """
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No video file provided"
        )

    allowed_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    file_extension = Path(file.filename).suffix.lower()

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail="Unsupported video format"
        )

    video_id = str(uuid.uuid4())
    filename = f"{video_id}{file_extension}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    video_path = upload_dir / filename

    try:
        with open(video_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save video: {str(e)}"
        )
    finally:
        await file.close()

    return filename, video_path


def remove_file(path: Path) -> None:
    """Safely removes a file if it exists."""
    try:
        if path.exists():
            os.remove(path)
    except Exception:
        pass
