from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.config import RESULT_DIR
from core.database import is_connected, get_db
from datetime import datetime, timezone
from routers import video, investigate, cases, evidence, reports, persons

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
# STARTUP EVENT — verify MongoDB on boot
# --------------------------------------------------
@app.on_event("startup")
def on_startup():
    """Verify MongoDB connectivity on application startup."""
    db = get_db()
    if db is not None:
        print("[ForenSight] MongoDB is available — using database as primary store")
    else:
        print("[ForenSight] MongoDB is NOT available — using JSON fallback mode")


# --------------------------------------------------
# ROUTES
# --------------------------------------------------
@app.get("/")
def home():
    return {
        "message": "ForenSight AI Backend Running"
    }


@app.get("/mongodb-test")
def mongodb_test():
    """
    DIAGNOSTIC ONLY: Fully isolated round-trip to verify MongoDB writes.
    Must be removed or gated behind a debug flag before production use.
    """
    db = get_db()
    if db is None:
        return {"error": "MongoDB not connected"}
    
    print("[ForenSight] DIAGNOSTIC ONLY: Running /mongodb-test")
    
    try:
        coll = db["mongodb_test"]
        doc = {
            "test": True,
            "source": "ForenSight AI",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        insert_res = coll.insert_one(doc)
        inserted_id = insert_res.inserted_id
        
        # Read back
        read_doc = coll.find_one({"_id": inserted_id})
        read_back_success = read_doc is not None and read_doc.get("test") == True
        
        return {
            "database": db.name,
            "collection": "mongodb_test",
            "inserted_id": str(inserted_id),
            "read_back_success": read_back_success
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/db-status")
def db_status():
    """Health check endpoint for MongoDB connectivity."""
    connected = is_connected()
    db = get_db()
    db_name = db.name if db is not None else None

    collections_info = {}
    if db is not None:
        try:
            for name in db.list_collection_names():
                collections_info[name] = db[name].estimated_document_count()
        except Exception:
            pass

    return {
        "mongodb_connected": connected,
        "database": db_name,
        "collections": collections_info,
    }


# --------------------------------------------------
# ROUTERS
# --------------------------------------------------
app.include_router(video.router)
app.include_router(investigate.router)
app.include_router(cases.router)
app.include_router(evidence.router)
app.include_router(reports.router)
app.include_router(persons.router)