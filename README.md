# ForenSight AI — AI-Powered CCTV Forensic Analysis & Threat Detection System

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![YOLO11](https://img.shields.io/badge/Ultralytics-YOLO11-blue?style=flat)](https://github.com/ultralytics/ultralytics)
[![Gemini 3.6 Flash](https://img.shields.io/badge/Google%20GenAI-Gemini%203.6%20Flash-4285F4?style=flat&logo=google)](https://aistudio.google.com)
[![MongoDB](https://img.shields.io/badge/MongoDB-Atlas%20%2F%20Local-47A248?style=flat&logo=mongodb)](https://www.mongodb.com)

**ForenSight AI** is an intelligent CCTV surveillance and video forensic analysis platform designed for security teams, forensic investigators, and law enforcement. It ingests video footage, runs multi-object detection and tracking (ByteTrack), computes spatial and temporal threat metrics (brandishing, weapon proximity, persistent incidents), extracts multimodal suspect attributes (clothing, apparel, carried items) via Google Gemini, and allows investigators to explore evidence, reconstruct timelines, and interrogate footage using natural language.

---

## 🌟 Key Features

- **Automated Video Processing & Object Tracking**: Uses YOLO11 (`yolo11n.pt`) with ByteTrack for persistent multi-object tracking and bounding box overlays.
- **Web-Ready H.264 Playback**: Automatically transcodes annotated videos into H.264 (`yuv420p` + `faststart`) for instant HTML5 web playback and seek capabilities across all modern browsers.
- **Threat Scoring & Fusion Engine**: Evaluates lethal weapons (guns, pistols, rifles, knives), blunt weapons (bats, crowbars, axes), and suspicious unattended items. Flags armed suspect brandishing via spatial IoU and center-distance proximity.
- **Multimodal Visual Attribute Tagging**: Crops tracked targets and queries Google Gemini 3.6 Flash to describe apparel (e.g. *"black hoodie, red cap"*) and carried items. Elevates threats detected within visual attributes.
- **Live Progress Feedback**: Background non-blocking video analysis with real-time percentage progress bar and phase status reporting (`GET /analysis-progress/{analysis_id}`).
- **Interactive Forensic AI Assistant**: Chat with an AI investigator grounded directly in the video's detections, threat timeline, and tracked targets.
- **Investigation Cases & Cross-Collection Linking**: Organize analyses into cases (`open`, `pending`, `closed`). Linking an analysis propagates the case ID across investigations, detections, persons, evidence, and reports.
- **Forensic Person Search**: Query tracked suspects by analysis ID, case ID, track ID, or apparel/clothing keywords.
- **Printable Forensic Reports**: Generates formal incident documentation with one-click PDF export for evidentiary submission.

---

## 🛠️ Architecture & Tech Stack

```
   ┌────────────────────────────────────────────────────────┐
   │             Frontend (HTML5 / Vanilla CSS & JS)        │
   │  Dashboard • Cases • Evidence • Timeline • Reports • AI│
   └───────────────────────────┬────────────────────────────┘
                               │ HTTP / REST
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │                   FastAPI Backend                      │
   │      Uvicorn Server • Async Worker • CORS Enabled      │
   └─────────────┬───────────────────────────┬──────────────┘
                 │                           │
                 ▼                           ▼
   ┌───────────────────────────┐ ┌───────────────────────────┐
   │     Computer Vision       │ │       Generative AI       │
   │  Ultralytics YOLO11       │ │  Google Gemini 3.6 Flash  │
   │  ByteTrack Tracker        │ │  Multimodal Crop Analysis │
   │  OpenCV & imageio-ffmpeg  │ │  Forensic Chat Assistant  │
   └─────────────┬─────────────┘ └───────────┬───────────────┘
                 │                           │
                 └─────────────┬─────────────┘
                               │
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │                    Data Persistence                    │
   │   MongoDB (6 Collections) ──► Fallback to Local JSON   │
   └────────────────────────────────────────────────────────┘
```

---

## 📋 Prerequisites

- **Python**: 3.10 to 3.12+ recommended
- **Operating System**: Windows, Linux, or macOS
- **Google Gemini API Key**: Free tier available from [Google AI Studio](https://aistudio.google.com/apikey)
- **MongoDB**: MongoDB Atlas connection URI or local instance; required to complete and save video analyses

---

## ⚙️ Installation & Setup

### 1. Clone & Set Up Virtual Environment

```bash
# Clone the repository
git clone https://github.com/rohit24268/FE_Project.git
cd FE_Project

# Create and activate Python virtual environment
python -m venv .venv

# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# On Linux / macOS:
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create or edit `backend/.env`:

```env
# Required for AI Assistant & Multimodal Crop Analysis
GEMINI_API_KEY=your_gemini_api_key_here

# Required for video analysis, uploads, and analysis results
MONGODB_URI=mongodb+srv://USERNAME:PASSWORD@CLUSTER.mongodb.net/?retryWrites=true&w=majority
MONGODB_DATABASE=ForenSightAI
```

Each successfully analyzed video automatically creates the next numbered case collection (`case1`, `case2`, …) in MongoDB. Its GridFS bucket stores three files: the annotated video, complete analysis JSON, and threat-detections JSON. MongoDB exposes each bucket's file metadata in `caseN.files` and file contents in `caseN.chunks`; the `caseN` collection keeps a small manifest of the file IDs. Original uploads are not stored in MongoDB. Video analysis returns an error if MongoDB is unavailable or a save fails.

The upload and generated video are held in a temporary working directory only while analysis runs. The directory is automatically removed after the result is saved to MongoDB; analysis does not leave uploaded videos, annotated videos, or detection JSON files in the backend project folders.

---

## 🚀 Running the Application

### 1. Start the Backend API Server
```powershell
cd d:\FE_Project\backend
.\venv\Scripts\Activate.ps1 
uvicorn main:app --reload --port 8000
```
- API will run at: `http://localhost:8000`
- Interactive Swagger API docs: `http://localhost:8000/docs`

### 2. Start the Frontend Dashboard
In a separate terminal:
```powershell
cd d:\FE_Project\frontend
python -m http.server 5500
```
- Open your browser at: **`http://localhost:5500`**

---

## 📑 API Endpoints Summary

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/analyze-video` | Upload CCTV footage; runs YOLO tracking, Gemini attributes, and H.264 transcoding |
| `GET` | `/analysis-progress/{analysis_id}` | Poll real-time percentage and phase of video processing |
| `GET` | `/download-video/{filename}` | Download the annotated MP4 video file |
| `POST` | `/investigate` | Ask forensic questions to Gemini AI grounded in analysis data |
| `GET` | `/cases` | List all investigation cases |
| `POST` | `/cases` | Create a new case (`title`, `investigator`, `description`, `status`) |
| `GET` | `/evidence/{analysis_id}` | Retrieve formatted evidence records and chronological timeline |
| `GET` | `/reports/{analysis_id}` | Generate structured forensic report with findings and timeline |
| `GET` | `/search-persons` | Search tracked persons by `case_id`, `analysis_id`, `track_id`, or `attributes` |
| `GET` | `/db-status` | Health check for MongoDB connectivity and collection document counts |

---

## 🧪 Running Automated Tests

Run the test suite from the `backend/` folder:
```powershell
cd d:\FE_Project\backend
..\.venv\Scripts\python.exe -m unittest discover tests
```
All 13 unit and integration tests will execute and verify threat scoring, spatial proximity calculations, case management schemas, and API routes.

---

## ⚖️ License & Forensic Notice

Track IDs generated by ByteTrack are video-session scoped tracking identifiers and **do not** constitute facial recognition or real-world legal identity. Always cross-verify automated findings against the raw footage.
