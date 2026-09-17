from ultralytics import YOLO
from pathlib import Path
import cv2
import json
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


# --------------------------------------------------
# ANALYZE VIDEO
# --------------------------------------------------

def analyze_video(video_path: str, result_dir: str):

    result_path = Path(result_dir)
    result_path.mkdir(
        parents=True,
        exist_ok=True
    )

    analysis_id = str(uuid.uuid4())

    output_video = (
        result_path /
        f"{analysis_id}_annotated.mp4"
    )

    output_json = (
        result_path /
        f"{analysis_id}_detections.json"
    )

    output_threats_json = (
        result_path /
        f"{analysis_id}_threats.json"
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

    frame_number = 0
    processed_frames = 0


    print("--------------------------------")
    print("Starting YOLO analysis")
    print(f"Video FPS: {original_fps}")
    print(f"Resolution: {width}x{height}")
    print("--------------------------------")


    # --------------------------------------------------
    # PROCESS VIDEO
    # --------------------------------------------------

    while True:

        success, frame = cap.read()

        if not success:
            break


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


    # --------------------------------------------------
    # METHOD A: PARALLEL MULTIMODAL CROP ANALYSIS
    # --------------------------------------------------

    track_attributes = {}
    if track_crops:
        sample_crops = dict(list(track_crops.items())[:15])
        print("--------------------------------")
        print(f"Running Method A Parallel Multimodal Analysis on {len(sample_crops)} unique track(s)...")

        def _process_track_crop(item):
            tid, crop_bytes = item
            try:
                attr = analyze_crop_attributes(crop_bytes)
                if attr:
                    return tid, attr
            except Exception as e:
                print(f"Failed to analyze track #{tid}: {e}")
            return tid, None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(_process_track_crop, item) for item in sample_crops.items()]
            for future in as_completed(futures):
                tid, attr = future.result()
                if attr:
                    track_attributes[tid] = attr
                    print(f"Track #{tid} visual attributes: {attr}")

        print("--------------------------------")

    # Enrich detections with visual attributes
    for detection in detections:
        tid = detection.get("track_id")
        if tid in track_attributes:
            detection["attributes"] = track_attributes[tid]


    # --------------------------------------------------
    # SAVE DETECTIONS & THREAT ANALYSIS JSON
    # --------------------------------------------------

    with open(
        output_json,
        "w"
    ) as file:

        json.dump(
            detections,
            file,
            indent=4
        )

    threat_analysis = analyze_video_threats(detections)

    with open(
        output_threats_json,
        "w"
    ) as file:

        json.dump(
            threat_analysis,
            file,
            indent=4
        )


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

        "detections_file":
            str(output_json),

        "threats_file":
            str(output_threats_json),

        "total_detections":
            len(detections),

        "object_counts":
            object_counts,

        "threat_analysis":
            threat_analysis,

        "detections":
            detections
    }