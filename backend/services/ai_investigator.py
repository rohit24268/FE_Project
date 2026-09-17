import os
from collections import defaultdict

from google import genai
from google.genai import types
from google.genai import errors as genai_errors


# --------------------------------------------------
# CLIENT
# --------------------------------------------------

# The API key is read from the GEMINI_API_KEY (or GOOGLE_API_KEY)
# environment variable automatically. Set it in a local .env
# file (already gitignored) or your shell environment before
# running the server. Get a free key at https://aistudio.google.com/apikey

_client = None


def _get_client():

    global _client

    if _client is None:
        _client = genai.Client()

    return _client


# Gemini Flash model via Google AI Studio.
MODEL = "gemini-3.6-flash"

MAX_SAMPLE_EVENTS = 400


# --------------------------------------------------
# MULTIMODAL CROP ANALYSIS (METHOD A)
# --------------------------------------------------

def analyze_crop_attributes(image_bytes: bytes) -> str:
    """
    Analyzes a cropped object image using Gemini 3.6 Flash multimodal capabilities
    and returns a concise description of visual attributes (clothing color, type, vehicle color, etc.).
    """
    if not image_bytes:
        return ""

    try:
        client = _get_client()
        image_part = types.Part.from_bytes(
            data=image_bytes,
            mime_type="image/jpeg"
        )
        prompt = (
            "In 1 short sentence (under 12 words), describe the visual attributes of "
            "this detected object/person from CCTV (e.g. clothing color and apparel if person, "
            "vehicle color and type if vehicle)."
        )
        response = client.models.generate_content(
            model=MODEL,
            contents=[image_part, prompt],
            config=types.GenerateContentConfig(
                max_output_tokens=60,
                temperature=0.2,
            )
        )
        return (response.text or "").strip()
    except Exception as e:
        print(f"Crop analysis error: {e}")
        return ""


# --------------------------------------------------
# BUILD CASE CONTEXT FROM RAW DETECTIONS & THREATS
# --------------------------------------------------

def build_case_context(detections: list, threat_analysis: dict | None = None) -> str:
    """
    Turns raw detections and threat analysis into a compact,
    threat-focused forensic summary that Gemini can reason over.
    """

    if not detections:
        return "No objects were detected in this footage."

    # Compute threat analysis if not provided
    if threat_analysis is None:
        try:
            from services.threat_service import analyze_video_threats
            threat_analysis = analyze_video_threats(detections)
        except Exception as e:
            print(f"Failed to compute threats on the fly: {e}")
            threat_analysis = None

    lines = []

    # 1. THREAT ASSESSMENT HEADER
    if threat_analysis:
        lines.append("=== THREAT ASSESSMENT SUMMARY ===")
        lines.append(f"Overall Threat Level: {threat_analysis.get('overall_threat_level', 'UNKNOWN')}")
        lines.append(f"Peak Threat Risk Score: {threat_analysis.get('max_threat_score', 0.0)}")
        lines.append(f"Total Incident Count: {threat_analysis.get('total_incidents', 0)}")

        incidents = threat_analysis.get("incidents", [])
        if incidents:
            lines.append("\n=== INCIDENT TIMELINE ===")
            for idx, inc in enumerate(incidents, 1):
                types_str = ", ".join(inc.get("threat_types", []))
                armed_str = "YES (Weapon held/adjacent to person)" if inc.get("armed_person") else "NO"
                lines.append(
                    f"- Incident #{idx}: {inc.get('start_time', 0.0):.2f}s to {inc.get('end_time', 0.0):.2f}s "
                    f"(Duration: {inc.get('duration', 0.0):.2f}s) | Severity: {inc.get('peak_level', 'UNKNOWN')} "
                    f"(Score: {inc.get('peak_score', 0.0):.2f}) | Threat Types: [{types_str}] | Armed Suspect: {armed_str}"
                )
        else:
            lines.append("\nNo high-severity threat incidents were flagged.")

        threat_summary = threat_analysis.get("threat_summary", {})
        seen_objs = threat_summary.get("threat_objects_seen", {})
        if seen_objs:
            lines.append("\nThreat Objects Detected:")
            for obj_name, cnt in seen_objs.items():
                lines.append(f"- {obj_name}: {cnt} frame occurrence(s)")

        lines.append("")

    # 2. GENERAL DETECTIONS & TRACKS
    object_counts = defaultdict(int)
    first_seen = {}
    last_seen = {}
    track_ids_by_object = defaultdict(set)
    track_attributes = {}

    for d in detections:
        obj = d.get("object", "unknown")
        ts = d.get("timestamp", 0)
        track_id = d.get("track_id")
        attr = d.get("attributes")

        object_counts[obj] += 1

        if obj not in first_seen or ts < first_seen[obj]:
            first_seen[obj] = ts

        if obj not in last_seen or ts > last_seen[obj]:
            last_seen[obj] = ts

        if track_id is not None:
            track_ids_by_object[obj].add(track_id)
            if attr and track_id not in track_attributes:
                track_attributes[track_id] = attr

    total_duration = max(last_seen.values()) if last_seen else 0

    lines.append("=== GENERAL OBJECT DETECTION SUMMARY ===")
    lines.append(f"Total detection events: {len(detections)}")
    lines.append(f"Footage duration covered: ~{total_duration:.1f} seconds")
    lines.append("Detected entities:")
    for obj, count in sorted(object_counts.items(), key=lambda x: -x[1]):
        unique_tracks = len(track_ids_by_object.get(obj, set()))
        lines.append(
            f"- {obj}: {count} detection events, "
            f"{unique_tracks} unique tracked instance(s), "
            f"first seen at {first_seen[obj]:.2f}s, "
            f"last seen at {last_seen[obj]:.2f}s"
        )

    if track_attributes:
        lines.append("\n=== TRACKED TARGET VISUAL ATTRIBUTES (Multimodal Analysis) ===")
        for tid, attr in sorted(track_attributes.items()):
            lines.append(f"- Track ID #{tid}: {attr}")

    # 3. SAMPLE EVENT LOG
    step = max(1, len(detections) // MAX_SAMPLE_EVENTS)
    sampled = detections[::step][:MAX_SAMPLE_EVENTS]

    event_lines = [
        "\n=== SAMPLED EVENT LOG "
        "(frame, timestamp_s, object, track_id, confidence, bbox, is_threat, threat_cat, attributes) ==="
    ]

    for d in sampled:
        bbox = d.get("bounding_box", {})
        attr = d.get("attributes", "")
        attr_str = f", attr: '{attr}'" if attr else ""
        is_threat = d.get("is_threat", False)
        threat_cat = d.get("threat_category", "")
        threat_str = f", THREAT: {threat_cat}" if is_threat else ""

        event_lines.append(
            f"{d.get('frame')}, {d.get('timestamp')}, "
            f"{d.get('object')}, {d.get('track_id')}, "
            f"{d.get('confidence')}, "
            f"[{bbox.get('x1')},{bbox.get('y1')},"
            f"{bbox.get('x2')},{bbox.get('y2')}]"
            f"{threat_str}{attr_str}"
        )

    return "\n".join(lines) + "\n" + "\n".join(event_lines)


# --------------------------------------------------
# ASK THE ASSISTANT A QUESTION
# --------------------------------------------------

SYSTEM_PROMPT = """You are the Threat & Incident Response AI Forensic Analyst inside \
ForenSight AI, a CCTV threat detection and forensic investigation system.

Your primary mission is to assist law enforcement, security personnel, and investigators \
by identifying security threats, analyzing armed individuals, reconstructing incident timelines, \
and generating dispatch or forensic reports based on YOLO detections and multi-model threat analysis.

You are provided with:
1. A Threat Assessment Summary (Overall Threat Level: SAFE, LOW, MEDIUM, HIGH, CRITICAL, Peak Threat Risk Score, Total Incidents).
2. An Incident Timeline log (start time, end time, duration, peak severity, threat types, and whether an armed individual was detected).
3. Tracked Target Visual Attributes (clothing, apparel, vehicle characteristics from multimodal CCTV crop analysis).
4. General object detection summary and sampled frame event logs.

Rules:
- Prioritize safety and threat awareness: immediately highlight any detected lethal weapons (guns, knives, firearms), blunt weapons, brandishing behaviors, or suspicious items when relevant to the question.
- Always cite exact timestamps, durations, and Track IDs (e.g. "Track ID #2 brandished a knife between 00:14.2s and 00:22.5s") so investigators can verify the footage directly.
- Maintain a professional, objective, forensic tone. Distinguish clearly between confirmed weapon detections and unconfirmed/suspicious items.
- If asked to summarize incidents or write a report, structure it clearly with: Threat Level, Incident Timeline, Involved Suspects/Track IDs, Visual Descriptions, and Recommended Actionable Next Steps (e.g. security dispatch, area perimeter lockdown).
- Answer strictly from the provided case data. If information is missing or not detected in the footage, state that clearly rather than inventing details.
"""


class InvestigatorRateLimitError(Exception):
    """Raised when the Gemini free-tier rate limit is hit."""
    pass


def ask_investigator(
    detections: list,
    question: str,
    history: list | None = None,
    threat_analysis: dict | None = None,
) -> str:

    context = build_case_context(detections, threat_analysis=threat_analysis)

    # --------------------------------------------------
    # BUILD MULTI-TURN CONTENTS
    # --------------------------------------------------
    # Gemini uses "user" / "model" roles (not "assistant"),
    # and each turn's text goes inside a "parts" list.

    contents = []

    if history:
        for turn in history:

            role = turn.get("role")
            text = turn.get("content")

            if not text:
                continue

            if role == "user":
                contents.append(
                    {"role": "user", "parts": [{"text": text}]}
                )
            elif role == "assistant":
                contents.append(
                    {"role": "model", "parts": [{"text": text}]}
                )

    contents.append(
        {
            "role": "user",
            "parts": [
                {
                    "text": (
                        f"CASE DATA:\n{context}\n\n"
                        f"INVESTIGATOR QUESTION: {question}"
                    )
                }
            ],
        }
    )

    client = _get_client()

    try:

        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=1024,
            ),
        )

    except genai_errors.ClientError as e:

        if getattr(e, "code", None) == 429:

            raise InvestigatorRateLimitError(
                "The AI Investigation Assistant is temporarily "
                "rate-limited (Gemini free tier). Please wait a "
                "minute and try again."
            )

        raise

    return (response.text or "").strip()