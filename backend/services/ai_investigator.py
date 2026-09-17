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
# BUILD CASE CONTEXT FROM RAW DETECTIONS
# --------------------------------------------------

def build_case_context(detections: list) -> str:
    """
    Turns the raw per-frame detections list into a compact,
    token-efficient summary + a sampled event log that Gemini
    can reason over directly, instead of dumping the entire
    (potentially huge) JSON file into the prompt.
    """

    if not detections:
        return "No objects were detected in this footage."

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

    summary_lines = [
        f"Total detection events: {len(detections)}",
        f"Footage duration covered by detections: ~{total_duration:.1f} seconds",
        "",
        "Per-object summary:",
    ]

    for obj, count in sorted(
        object_counts.items(), key=lambda x: -x[1]
    ):

        unique_tracks = len(track_ids_by_object.get(obj, set()))

        summary_lines.append(
            f"- {obj}: {count} detection events, "
            f"{unique_tracks} unique tracked instance(s), "
            f"first seen at {first_seen[obj]:.2f}s, "
            f"last seen at {last_seen[obj]:.2f}s"
        )

    if track_attributes:
        summary_lines.append("\nTracked Target Visual Attributes (Method A Multimodal Analysis):")
        for tid, attr in sorted(track_attributes.items()):
            summary_lines.append(f"- Track ID #{tid}: {attr}")

    # --------------------------------------------------
    # SAMPLE EVENT LOG (kept small to control token usage)
    # --------------------------------------------------

    step = max(1, len(detections) // MAX_SAMPLE_EVENTS)
    sampled = detections[::step][:MAX_SAMPLE_EVENTS]

    event_lines = [
        "\nSampled detection event log "
        "(frame, timestamp_s, object, track_id, confidence, bbox, attributes):"
    ]

    for d in sampled:

        bbox = d.get("bounding_box", {})
        attr = d.get("attributes", "")
        attr_str = f", attributes: '{attr}'" if attr else ""

        event_lines.append(
            f"{d.get('frame')}, {d.get('timestamp')}, "
            f"{d.get('object')}, {d.get('track_id')}, "
            f"{d.get('confidence')}, "
            f"[{bbox.get('x1')},{bbox.get('y1')},"
            f"{bbox.get('x2')},{bbox.get('y2')}]"
            f"{attr_str}"
        )

    return "\n".join(summary_lines) + "\n" + "\n".join(event_lines)


# --------------------------------------------------
# ASK THE ASSISTANT A QUESTION
# --------------------------------------------------

SYSTEM_PROMPT = """You are the AI Investigation Assistant inside \
ForenSight AI, a forensic CCTV analysis tool. You help investigators \
make sense of YOLO object-detection results extracted from a single \
piece of CCTV footage.

You will be given:
1. A summary of detected objects (counts, first/last appearance times, \
number of uniquely tracked instances).
2. A sampled log of individual detection events (frame number, \
timestamp in seconds, object class, track ID, confidence, bounding box).

Rules:
- Answer strictly based on the provided detection data. Never invent \
objects, people, timestamps, or events that are not supported by it.
- The event log is a SAMPLE, not the complete list, so be careful with \
exact counts if the sample looks incomplete for a question — say so \
and refer the investigator to the full JSON export when precision \
matters.
- When useful, cite specific timestamps, frame numbers, or track IDs \
so the investigator can locate the moment in the footage.
- Keep answers concise and factual, in a neutral investigative tone. \
Do not speculate about identity, intent, or guilt of any person or \
vehicle shown — you are reporting object-detection evidence only.
- If the data doesn't contain enough information to answer, say so \
plainly instead of guessing.
"""


class InvestigatorRateLimitError(Exception):
    """Raised when the Gemini free-tier rate limit is hit."""
    pass


def ask_investigator(
    detections: list,
    question: str,
    history: list | None = None,
) -> str:

    context = build_case_context(detections)

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