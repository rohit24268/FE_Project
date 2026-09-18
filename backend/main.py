from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import RESULT_DIR
from routers import video, investigate, cases, evidence, reports

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
# SERVE PROCESSED RESULTS
# --------------------------------------------------
app.mount(
    "/results",
    StaticFiles(directory=str(RESULT_DIR)),
    name="results"
)

# --------------------------------------------------
# ROUTERS
# --------------------------------------------------
@app.get("/")
def home():
    return {
        "message": "ForenSight AI Backend Running"
    }

app.include_router(video.router)
app.include_router(investigate.router)
app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(reports.router)