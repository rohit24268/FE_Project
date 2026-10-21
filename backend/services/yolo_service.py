from ultralytics import YOLO
from pathlib import Path
import cv2
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from services.ai_investigator import analyze_crop_attributes
from services.threat_service import (
    get_base_threat_weight,
    score_frame_threat,
    analyze_video_threats,
)


# --------------------------------------------------
# LOAD YOLO MODEL ONCE
# --------------------------------------------------

MODEL_PATH = Path(__file__).resolve().parent.parent / "yolo11n.pt"
model = YOLO(str(MODEL_PATH))


def transcode_to_h264(input_video_path: Path) -> bool:
    """
    Transcode an OpenCV mp4v video into browser-friendly H.264 (yuv420p)
    using imageio_ffmpeg or system ffmpeg with +faststart for instant streaming.
    Guarantees seamless HTML5 <video> playback across Chrome, Edge, Safari, Firefox.
    """
    import subprocess
    import shutil
    
    ffmpeg_exe = None
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg_exe = shutil.which("ffmpeg")

    if not ffmpeg_exe:
        return False

    temp_output = input_video_path.with_name(f"{input_video_path.stem}_h264.mp4")
    try:
        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", str(input_video_path),
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-an",
            str(temp_output),
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and temp_output.exists() and temp_output.stat().st_size > 0:
            temp_output.replace(input_video_path)
            print(f"[ForenSight AI] Video transcoded to web-compatible H.264: {input_video_path.name}")
            return True
        else:
            err = res.stderr.decode("utf-8", errors="ignore")[:200]
            print(f"[ForenSight AI] Transcoding warning: {err}")
    except Exception as e:
        print(f"[ForenSight AI] Transcoding error: {e}")
    finally:
        if temp_output.exists():
            try:
                temp_output.unlink()
            except Exception:
                pass
    return False


# --------------------------------------------------
# ANALYZE VIDEO
# --------------------------------------------------

def analyze_video(
    video_path: str,
    result_dir: str,
    analysis_id: str | None = None,
    progress_callback = None
):

    result_path = Path(result_dir)
    result_path.mkdir(
        parents=True,
        exist_ok=True
    )

    if not analysis_id:
        analysis_id = str(uuid.uuid4())

    output_video = (
        result_path /
        f"{analysis_id}_annotated.mp4"
    )

    # --------------------------------------------------
    # OPEN VIDEO
    # --------------------------------------------------

    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise ValueError(
            "Unable to open video file"
        )


    # --------------------------------------------------
    # VIDEO INFORMATION
    # --------------------------------------------------

    original_fps = cap.get(
        cv2.CAP_PROP_FPS
    )

    if original_fps <= 0:
        original_fps = 30

    width = int(
        cap.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    height = int(
        cap.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )


    # --------------------------------------------------
    # OUTPUT VIDEO
    # --------------------------------------------------

    fourcc = cv2.VideoWriter_fourcc(
        *"mp4v"
    )

    writer = cv2.VideoWriter(
        str(output_video),
        fourcc,
        original_fps,
        (width, height)
    )

    if not writer.isOpened():

        cap.release()

        raise ValueError(
            "Unable to create output video"
        )


    # --------------------------------------------------
    # SETTINGS
    # --------------------------------------------------

    # Process approximately 10 FPS
    # instead of every frame.
    FRAME_SKIP = 3

    CONFIDENCE = 0.40

    # YOLO inference size
    IMAGE_SIZE = 640


    # --------------------------------------------------
    # STORAGE
    # --------------------------------------------------

    detections = []
    track_crops = {}

    total_raw_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_raw_frames <= 0:
        total_raw_frames = 100

    frame_number = 0
    processed_frames = 0

    if progress_callback:
        progress_callback(5, "Starting YOLO detection & tracking...")

    print("--------------------------------")
    print("Starting YOLO analysis")
    print(f"Video FPS: {original_fps}")
    print(f"Resolution: {width}x{height}")
    print(f"Total Frames: {total_raw_frames}")
    print("--------------------------------")


    # --------------------------------------------------
    # PROCESS VIDEO
    # --------------------------------------------------

    while True:

        success, frame = cap.read()

        if not success:
            break

        if progress_callback and frame_number % 15 == 0 and total_raw_frames > 0:
            pct = min(75, max(5, int((frame_number / total_raw_frames) * 75)))
            progress_callback(pct, f"Processing video frames ({frame_number}/{total_raw_frames})...")

        # --------------------------------------------------
        # PROCESS ONLY EVERY 3RD FRAME
        # --------------------------------------------------

        if frame_number % FRAME_SKIP != 0:

            # Write original frame so
            # output video keeps correct FPS.
            writer.write(frame)

            frame_number += 1

            continue


        processed_frames += 1


        # --------------------------------------------------
        # YOLO + BYTE TRACK
        # --------------------------------------------------

        results = model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            conf=CONFIDENCE,
            imgsz=IMAGE_SIZE,
            verbose=False
        )


        # --------------------------------------------------
        # DETECTIONS
        # --------------------------------------------------

        current_frame_detections = []

        for result in results:

            if result.boxes is None:
                continue


            for box in result.boxes:

                # Class
                class_id = int(
                    box.cls[0]
                )

                object_name = model.names[
                    class_id
                ]


                # Confidence
                confidence = float(
                    box.conf[0]
                )


                # Bounding box
                x1, y1, x2, y2 = map(
                    int,
                    box.xyxy[0]
                )


                # Track ID
                track_id = None

                if box.id is not None:
                    track_id = int(
                        box.id[0]
                    )
                    if track_id not in track_crops:
                        h, w, _ = frame.shape
                        cy1, cy2 = max(0, y1), min(h, y2)
                        cx1, cx2 = max(0, x1), min(w, x2)
                        if (cy2 - cy1) > 20 and (cx2 - cx1) > 20:
                            crop = frame[cy1:cy2, cx1:cx2]
                            success_enc, encoded_img = cv2.imencode(".jpg", crop)
                            if success_enc:
                                track_crops[track_id] = encoded_img.tobytes()


                # Timestamp
                timestamp = (
                    frame_number /
                    original_fps
                )

                # Threat Classification
                base_weight, threat_cat = get_base_threat_weight(object_name)

                detection = {

                    "frame":
                        frame_number,

                    "timestamp":
                        round(
                            timestamp,
                            3
                        ),

                    "object":
                        object_name,

                    "confidence":
                        round(
                            confidence,
                            3
                        ),

                    "track_id":
                        track_id,

                    "is_threat":
                        threat_cat != "NONE",

                    "threat_category":
                        threat_cat,

                    "bounding_box": {

                        "x1": x1,

                        "y1": y1,

                        "x2": x2,

                        "y2": y2
                    }
                }


                detections.append(
                    detection
                )
                current_frame_detections.append(
                    detection
                )


        # --------------------------------------------------
        # DRAW DETECTIONS & THREAT OVERLAY
        # --------------------------------------------------

        annotated_frame = results[0].plot()

        # Threat Alert Overlay
        f_threat = score_frame_threat(current_frame_detections)
        if f_threat["threat_level"] in ("HIGH", "CRITICAL"):
            threat_names = ", ".join(set(o["object"] for o in f_threat["threat_objects"]))
            alert_text = f"THREAT ALERT: {f_threat['threat_level']} [{threat_names}]"
            cv2.putText(
                annotated_frame,
                alert_text,
                (20, 45),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.85,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )
        elif f_threat["threat_level"] == "MEDIUM":
            alert_text = f"CAUTION: {f_threat['threat_level']} THREAT DETECTED"
            cv2.putText(
                annotated_frame,
                alert_text,
                (20, 45),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (0, 165, 255),
                2,
                cv2.LINE_AA,
            )


        # --------------------------------------------------
        # WRITE ANNOTATED FRAME
        # --------------------------------------------------

        writer.write(
            annotated_frame
        )


        frame_number += 1


        # --------------------------------------------------
        # PROGRESS
        # --------------------------------------------------

        if processed_frames % 30 == 0:

            print(
                f"Processed "
                f"{processed_frames} YOLO frames..."
            )


    # --------------------------------------------------
    # RELEASE
    # --------------------------------------------------

    cap.release()
    writer.release()

    if progress_callback:
        progress_callback(78, "Running AI visual attribute analysis on tracked targets...")

    # --------------------------------------------------
    # METHOD A: PARALLEL MULTIMODAL CROP ANALYSIS
    # --------------------------------------------------

    track_attributes = {}
    if track_crops:
        # Sample up to 8 distinct tracks to stay comfortably within Gemini free-tier limits
        sample_crops = dict(list(track_crops.items())[:8])
        print("--------------------------------")
        print(f"Running Multimodal Crop Analysis on {len(sample_crops)} unique track(s)...")

        def _process_track_crop(item):
            tid, crop_bytes = item
            try:
                attr = analyze_crop_attributes(crop_bytes)
                if attr:
                    return tid, attr
            except Exception as e:
                print(f"Failed to analyze track #{tid}: {e}")
            return tid, None

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(_process_track_crop, item) for item in sample_crops.items()]
            for future in as_completed(futures):
                tid, attr = future.result()
                if attr:
                    track_attributes[tid] = attr
                    print(f"Track #{tid} visual attributes: {attr}")

        print("--------------------------------")

    # Enrich detections with visual attributes & detect weapons identified by Multimodal AI
    WEAPON_KEYWORDS = ["gun", "pistol", "rifle", "firearm", "knife", "dagger", "sword", "weapon", "blade", "crowbar", "axe"]
    for detection in detections:
        tid = detection.get("track_id")
        if tid in track_attributes:
            attr = track_attributes[tid]
            detection["attributes"] = attr
            attr_lower = attr.lower()
            if any(w in attr_lower for w in WEAPON_KEYWORDS):
                detection["is_threat"] = True
                if any(w in attr_lower for w in ["gun", "pistol", "rifle", "firearm", "weapon"]):
                    detection["threat_category"] = "LETHAL_WEAPON"
                elif any(w in attr_lower for w in ["knife", "dagger", "sword", "blade"]):
                    detection["threat_category"] = "LETHAL_WEAPON"
                else:
                    detection["threat_category"] = "BLUNT_WEAPON"

    if progress_callback:
        progress_callback(88, "Computing forensic threat fusion & timeline...")

    threat_analysis = analyze_video_threats(detections)

    if progress_callback:
        progress_callback(93, "Transcoding annotated video for web playback...")

    # Transcode video to standard web-compatible H.264 (yuv420p)
    transcode_to_h264(output_video)

    if progress_callback:
        progress_callback(100, "Analysis complete")


    # --------------------------------------------------
    # OBJECT COUNTS
    # --------------------------------------------------

    object_counts = {}


    for detection in detections:

        object_name = (
            detection["object"]
        )

        object_counts[
            object_name
        ] = (
            object_counts.get(
                object_name,
                0
            ) + 1
        )


    # --------------------------------------------------
    # FINAL LOG
    # --------------------------------------------------

    print("--------------------------------")
    print("YOLO analysis completed")
    print(
        f"Total video frames: "
        f"{frame_number}"
    )
    print(
        f"YOLO processed frames: "
        f"{processed_frames}"
    )
    print(
        f"Total detections: "
        f"{len(detections)}"
    )
    print(
        f"Threat Level: {threat_analysis['overall_threat_level']} "
        f"(Peak Score: {threat_analysis['max_threat_score']}, "
        f"Incidents: {threat_analysis['total_incidents']})"
    )
    print("--------------------------------")


    # --------------------------------------------------
    # RETURN RESULT
    # --------------------------------------------------

    return {

        "analysis_id":
            analysis_id,

        "video":
            str(output_video),

        "total_detections":
            len(detections),

        "object_counts":
            object_counts,

        "threat_analysis":
            threat_analysis,

        "detections":
            detections
    }