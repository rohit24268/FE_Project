import os
import time
from pathlib import Path
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import cv2
import torch
from ultralytics import YOLO

from services.ai_investigator import analyze_crop_attributes, is_gemini_available
from services.threat_service import (
    get_base_threat_weight,
    score_frame_threat,
    analyze_video_threats,
)
from services.weapon_detection_service import (
    detect_weapons_in_frame,
    deduplicate_weapon_detections,
    is_weapon_model_available,
)
from services.fire_smoke_service import (
    detect_fire_smoke_in_frame,
    deduplicate_fire_smoke_detections,
    group_fire_smoke_events,
    is_fire_smoke_model_available,
)

# --------------------------------------------------
# HARDWARE ACCELERATION & MODEL INITIALIZATION
# --------------------------------------------------

# Automatic GPU detection (CUDA) with safe CPU fallback
_DEVICE = 0 if torch.cuda.is_available() else "cpu"

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
    # PERFORMANCE & SAMPLING CONFIGURATION
    # --------------------------------------------------

    # Configurable sampling rate (default 5 FPS: ~150 frames for 30s video)
    ANALYSIS_FPS = max(0.5, float(os.environ.get("ANALYSIS_FPS", "5.0")))
    FIRE_SMOKE_FPS = max(0.5, float(os.environ.get("FIRE_SMOKE_SAMPLE_FPS", str(ANALYSIS_FPS))))
    WEAPON_FPS = max(0.5, float(os.environ.get("WEAPON_SAMPLE_FPS", str(ANALYSIS_FPS))))
    IMAGE_SIZE = int(os.environ.get("YOLO_IMAGE_SIZE", "640"))
    CONFIDENCE = float(os.environ.get("YOLO_CONFIDENCE", "0.40"))
    PRESERVE_ALL_FRAMES = os.environ.get("PRESERVE_ALL_FRAMES_IN_VIDEO", "false").lower() in ("true", "1")

    # Calculate frame step intervals
    sample_step = max(1, int(round(original_fps / ANALYSIS_FPS)))
    actual_sample_fps = original_fps / sample_step

    fs_step = max(1, int(round(original_fps / FIRE_SMOKE_FPS)))
    weapon_step = max(1, int(round(original_fps / WEAPON_FPS)))

    # Output VideoWriter: sampled FPS for fast playback, or full FPS if requested
    output_fps = original_fps if PRESERVE_ALL_FRAMES else actual_sample_fps

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(
        str(output_video),
        fourcc,
        output_fps,
        (width, height)
    )

    if not writer.isOpened():
        cap.release()
        raise ValueError("Unable to create output video")

    # --------------------------------------------------
    # STORAGE & PERFORMANCE TIMERS
    # --------------------------------------------------

    detections = []
    weapon_detections_raw = []
    fire_smoke_detections_raw = []
    track_crops = {}

    total_raw_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_raw_frames <= 0:
        total_raw_frames = 100

    frame_number = 0
    processed_frames = 0
    last_analyzed_frame_idx = -1
    last_annotated_frame = None

    t_start_total = time.perf_counter()
    total_decode_time = 0.0
    total_yolo_time = 0.0
    total_weapon_time = 0.0
    total_fire_smoke_time = 0.0
    total_annotation_time = 0.0

    if progress_callback:
        progress_callback(5, "Starting optimized YOLO detection & tracking...")

    print("--------------------------------")
    print(f"Starting ForenSight AI Analysis (Device: {str(_DEVICE).upper()})")
    print(f"Video FPS: {original_fps:.2f} | Resolution: {width}x{height} | Total Frames: {total_raw_frames}")
    print(f"Sampling: Every {sample_step} frames (~{actual_sample_fps:.1f} FPS target, {int(total_raw_frames / sample_step)} frames estimated)")
    print("--------------------------------")

    # --------------------------------------------------
    # OPTIMIZED VIDEO PROCESSING LOOP
    # --------------------------------------------------

    while True:
        is_sampled = (frame_number % sample_step == 0)

        # Ensure the last relevant portion of the video is not silently skipped
        if not is_sampled and total_raw_frames > 0:
            frames_remaining = (total_raw_frames - 1) - frame_number
            if frames_remaining == 0 and (frame_number - last_analyzed_frame_idx) >= max(1, sample_step // 2):
                is_sampled = True

        t_dec0 = time.perf_counter()
        if is_sampled or PRESERVE_ALL_FRAMES:
            success, frame = cap.read()
            total_decode_time += (time.perf_counter() - t_dec0)
            if not success:
                break
        else:
            # Fast frame advance using cap.grab() without pixel decoding
            has_more = cap.grab()
            total_decode_time += (time.perf_counter() - t_dec0)
            if not has_more:
                break
            frame_number += 1
            continue

        # If preserving full video FPS and this frame was skipped for AI inference
        if not is_sampled and PRESERVE_ALL_FRAMES:
            t_ann0 = time.perf_counter()
            writer.write(last_annotated_frame if last_annotated_frame is not None else frame)
            total_annotation_time += (time.perf_counter() - t_ann0)
            frame_number += 1
            continue

        processed_frames += 1
        last_analyzed_frame_idx = frame_number

        if progress_callback and processed_frames % 5 == 0 and total_raw_frames > 0:
            pct = min(75, max(5, int((frame_number / total_raw_frames) * 75)))
            progress_callback(pct, f"Analyzing frames ({processed_frames} sampled / {frame_number} read)...")

        # --------------------------------------------------
        # 1. YOLO + BYTE TRACK (INFERENCE MODE)
        # --------------------------------------------------

        t_y0 = time.perf_counter()
        with torch.inference_mode():
            results = model.track(
                frame,
                persist=True,
                tracker="bytetrack.yaml",
                conf=CONFIDENCE,
                imgsz=IMAGE_SIZE,
                verbose=False,
                device=_DEVICE,
            )
        total_yolo_time += (time.perf_counter() - t_y0)

        # --------------------------------------------------
        # DETECTIONS
        # --------------------------------------------------

        current_frame_detections = []

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                class_id = int(box.cls[0])
                object_name = model.names[class_id]
                confidence = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])

                track_id = None
                if box.id is not None:
                    track_id = int(box.id[0])
                    if track_id not in track_crops:
                        h, w, _ = frame.shape
                        cy1, cy2 = max(0, y1), min(h, y2)
                        cx1, cx2 = max(0, x1), min(w, x2)
                        if (cy2 - cy1) > 20 and (cx2 - cx1) > 20:
                            crop = frame[cy1:cy2, cx1:cx2]
                            success_enc, encoded_img = cv2.imencode(".jpg", crop)
                            if success_enc:
                                track_crops[track_id] = encoded_img.tobytes()

                timestamp = frame_number / original_fps
                base_weight, threat_cat = get_base_threat_weight(object_name)

                detection = {
                    "frame": frame_number,
                    "frame_number": frame_number,
                    "timestamp": round(timestamp, 3),
                    "object": object_name,
                    "class_name": object_name,
                    "confidence": round(confidence, 3),
                    "track_id": track_id,
                    "is_threat": threat_cat != "NONE",
                    "threat_category": threat_cat,
                    "bounding_box": {
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2
                    },
                    "detection_type": "general_object",
                    "event_type": f"{object_name}_detected"
                }

                detections.append(detection)
                current_frame_detections.append(detection)

        # --------------------------------------------------
        # 2. WEAPON DETECTION (separate model, sampled)
        # --------------------------------------------------

        frame_weapon_dets = []
        if is_weapon_model_available() and (frame_number % weapon_step == 0):
            t_w0 = time.perf_counter()
            frame_weapon_dets = detect_weapons_in_frame(
                frame,
                frame_number,
                original_fps,
                confidence_threshold=CONFIDENCE,
                image_size=IMAGE_SIZE,
            )
            total_weapon_time += (time.perf_counter() - t_w0)
            weapon_detections_raw.extend(frame_weapon_dets)

        # --------------------------------------------------
        # 3. FIRE & SMOKE DETECTION (separate model, sampled)
        # --------------------------------------------------

        frame_fire_smoke_dets = []
        if is_fire_smoke_model_available() and (frame_number % fs_step == 0):
            t_fs0 = time.perf_counter()
            frame_fire_smoke_dets = detect_fire_smoke_in_frame(
                frame,
                frame_number,
                original_fps,
                confidence_threshold=0.35,
                image_size=IMAGE_SIZE,
            )
            total_fire_smoke_time += (time.perf_counter() - t_fs0)
            fire_smoke_detections_raw.extend(frame_fire_smoke_dets)

            # Integrate fire/smoke detections into unified frame & video detections
            for fsd in frame_fire_smoke_dets:
                fs_obj = fsd["class_name"]
                fs_conf = fsd["confidence"]
                bx1, by1, bx2, by2 = fsd["bounding_box"]
                fs_timestamp = round(frame_number / original_fps, 3)
                _, threat_cat = get_base_threat_weight(fs_obj)

                fs_unified = {
                    "frame": frame_number,
                    "frame_number": frame_number,
                    "timestamp": fs_timestamp,
                    "object": fs_obj,
                    "class_name": fs_obj,
                    "confidence": round(fs_conf, 3),
                    "track_id": None,
                    "is_threat": True,
                    "threat_category": threat_cat if threat_cat != "NONE" else ("FIRE_HAZARD" if fs_obj == "fire" else "SMOKE_HAZARD"),
                    "bounding_box": {
                        "x1": bx1,
                        "y1": by1,
                        "x2": bx2,
                        "y2": by2,
                    },
                    "detection_type": "fire_smoke",
                    "event_type": fsd.get("event_type", f"{fs_obj}_detected"),
                    "review_status": "requires_human_verification",
                }
                detections.append(fs_unified)
                current_frame_detections.append(fs_unified)

        # --------------------------------------------------
        # 4. DRAW DETECTIONS & THREAT OVERLAY
        # --------------------------------------------------

        annotated_frame = results[0].plot()

        # Draw detected weapon boxes on annotated frame
        if frame_weapon_dets:
            for wd in frame_weapon_dets:
                bx1, by1, bx2, by2 = wd["bounding_box"]
                cv2.rectangle(annotated_frame, (bx1, by1), (bx2, by2), (0, 0, 255), 2)
                w_label = f"{wd['class_name'].upper()} {wd['confidence']:.2f}"
                cv2.putText(
                    annotated_frame,
                    w_label,
                    (bx1, max(by1 - 8, 18)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2,
                )

        # Draw detected fire and smoke boxes on annotated frame
        if frame_fire_smoke_dets:
            for fsd in frame_fire_smoke_dets:
                bx1, by1, bx2, by2 = fsd["bounding_box"]
                is_fire = fsd["class_name"] == "fire"
                box_color = (0, 69, 255) if is_fire else (200, 160, 100)
                cv2.rectangle(annotated_frame, (bx1, by1), (bx2, by2), box_color, 2)
                fs_label = f"{fsd['class_name'].upper()} {fsd['confidence']:.2f}"
                cv2.putText(
                    annotated_frame,
                    fs_label,
                    (bx1, max(by1 - 8, 18)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    box_color,
                    2,
                )

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

        # Write annotated frame
        t_ann0 = time.perf_counter()
        writer.write(annotated_frame)
        total_annotation_time += (time.perf_counter() - t_ann0)
        last_annotated_frame = annotated_frame

        frame_number += 1

    # --------------------------------------------------
    # RELEASE VIDEO HANDLES
    # --------------------------------------------------

    cap.release()
    writer.release()

    if progress_callback:
        progress_callback(78, "Running AI visual attribute analysis on tracked targets...")

    # --------------------------------------------------
    # METHOD A: PARALLEL MULTIMODAL CROP ANALYSIS (IF CONFIGURED)
    # --------------------------------------------------

    track_attributes = {}
    if track_crops and is_gemini_available():
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
    t_tc0 = time.perf_counter()
    transcode_to_h264(output_video)
    total_transcode_time = time.perf_counter() - t_tc0

    if progress_callback:
        progress_callback(100, "Analysis complete")

    # --------------------------------------------------
    # OBJECT COUNTS
    # --------------------------------------------------

    object_counts = {}
    for detection in detections:
        object_name = detection["object"]
        object_counts[object_name] = object_counts.get(object_name, 0) + 1

    # --------------------------------------------------
    # DEDUPLICATE WEAPONS & FIRE/SMOKE DETECTIONS
    # --------------------------------------------------

    weapon_detections = deduplicate_weapon_detections(weapon_detections_raw)
    fire_smoke_detections = deduplicate_fire_smoke_detections(fire_smoke_detections_raw)
    fire_smoke_events = group_fire_smoke_events(fire_smoke_detections_raw)

    # --------------------------------------------------
    # PERFORMANCE METRICS COMPILATION
    # --------------------------------------------------

    total_analysis_time = time.perf_counter() - t_start_total
    video_duration = round(total_raw_frames / original_fps, 2) if original_fps > 0 else 0.0
    coverage_pct = round((processed_frames / total_raw_frames) * 100, 1) if total_raw_frames > 0 else 100.0
    processing_fps = round(processed_frames / total_analysis_time, 2) if total_analysis_time > 0 else 0.0
    speedup_realtime = round(video_duration / total_analysis_time, 2) if total_analysis_time > 0 else 0.0

    performance_metrics = {
        "device": str(_DEVICE).upper(),
        "video_duration_seconds": video_duration,
        "source_fps": round(original_fps, 2),
        "total_video_frames": total_raw_frames,
        "analyzed_frames": processed_frames,
        "skipped_frames": max(0, total_raw_frames - processed_frames),
        "sampling_rate_fps": round(actual_sample_fps, 2),
        "sampling_step": sample_step,
        "coverage_percentage": coverage_pct,
        "total_analysis_time_seconds": round(total_analysis_time, 3),
        "processing_speed_fps": processing_fps,
        "realtime_speedup_factor": speedup_realtime,
        "time_breakdown_seconds": {
            "video_decoding": round(total_decode_time, 3),
            "yolo_general_model": round(total_yolo_time, 3),
            "weapon_detection_model": round(total_weapon_time, 3),
            "fire_smoke_model": round(total_fire_smoke_time, 3),
            "video_annotation_write": round(total_annotation_time, 3),
            "h264_transcode": round(total_transcode_time, 3),
        },
        "forensic_sampling_notice": (
            f"Analyzed {processed_frames} of {total_raw_frames} frames ({coverage_pct}% coverage) "
            f"at ~{actual_sample_fps:.1f} FPS (stride: {sample_step}). "
            f"Original timestamps are preserved. Transient events shorter than "
            f"{sample_step / original_fps:.2f}s occurring entirely within skipped frames may not be recorded. "
            f"Configure ANALYSIS_FPS to increase sampling density if investigating rapid transient events."
        ),
    }

    # Attach performance metrics to threat_analysis as well
    if isinstance(threat_analysis, dict):
        threat_analysis["performance_metrics"] = performance_metrics

    # --------------------------------------------------
    # PERFORMANCE LOGGING BANNER
    # --------------------------------------------------

    print("==================================================")
    print("ForenSight AI Video Analysis Performance Summary:")
    print(f"  Device: {performance_metrics['device']}")
    print(f"  Video Duration: {video_duration}s ({total_raw_frames} frames @ {original_fps:.1f} FPS)")
    print(f"  Analyzed Frames: {processed_frames} ({coverage_pct}% coverage @ {actual_sample_fps:.1f} FPS)")
    print(f"  Total Analysis Time: {total_analysis_time:.2f}s ({speedup_realtime}x realtime, {processing_fps} FPS)")
    print(f"  Time Breakdown:")
    print(f"    - Video Decoding: {total_decode_time:.2f}s")
    print(f"    - General YOLO Tracker: {total_yolo_time:.2f}s")
    print(f"    - Weapon Detection: {total_weapon_time:.2f}s")
    print(f"    - Fire & Smoke Detection: {total_fire_smoke_time:.2f}s")
    print(f"    - Video Annotation: {total_annotation_time:.2f}s")
    print(f"    - H.264 Web Transcoding: {total_transcode_time:.2f}s")
    print(f"  Detections: {len(detections)} | Weapons: {len(weapon_detections)} | Fire/Smoke Events: {len(fire_smoke_events)}")
    print(f"  Threat Level: {threat_analysis['overall_threat_level']} (Score: {threat_analysis['max_threat_score']}, Incidents: {threat_analysis['total_incidents']})")
    print("==================================================")

    # --------------------------------------------------
    # SAVE STRUCTURED RESULTS IN RESULT DIR (JSON ARTIFACTS)
    # --------------------------------------------------

    analysis_payload = {
        "analysis_id": analysis_id,
        "video": str(output_video),
        "total_detections": len(detections),
        "object_counts": object_counts,
        "threat_analysis": threat_analysis,
        "detections": detections,
        "weapon_detections": weapon_detections,
        "fire_smoke_detections": fire_smoke_detections,
        "fire_smoke_events": fire_smoke_events,
        "performance_metrics": performance_metrics,
    }

    try:
        import json
        with open(result_path / f"{analysis_id}_result.json", "w", encoding="utf-8") as f:
            json.dump(analysis_payload, f, indent=2, default=str)
        with open(result_path / f"{analysis_id}_detections.json", "w", encoding="utf-8") as f:
            json.dump(detections, f, indent=2, default=str)
        with open(result_path / f"{analysis_id}_threats.json", "w", encoding="utf-8") as f:
            json.dump({
                "analysis_id": analysis_id,
                "threat_analysis": threat_analysis,
                "threat_detections": [d for d in detections if d.get("is_threat")],
                "weapon_detections": weapon_detections,
                "fire_smoke_detections": fire_smoke_detections,
                "fire_smoke_events": fire_smoke_events,
                "performance_metrics": performance_metrics,
            }, f, indent=2, default=str)
        with open(result_path / f"{analysis_id}_fire_smoke.json", "w", encoding="utf-8") as f:
            json.dump({
                "analysis_id": analysis_id,
                "fire_smoke_events": fire_smoke_events,
                "fire_smoke_detections": fire_smoke_detections,
                "performance_metrics": performance_metrics,
            }, f, indent=2, default=str)
        with open(result_path / f"{analysis_id}_performance.json", "w", encoding="utf-8") as f:
            json.dump(performance_metrics, f, indent=2, default=str)
    except Exception as e:
        print(f"[ForenSight AI] Warning: failed to save local result JSON: {e}")

    # --------------------------------------------------
    # RETURN RESULT
    # --------------------------------------------------

    return analysis_payload