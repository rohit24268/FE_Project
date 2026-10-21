import os
import sys
from pathlib import Path
import json

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from core.database import get_db
from routers.video import _persist_to_mongodb

def run_verification():
    db = get_db()
    if db is None:
        print("[Verify] MongoDB is not connected. Set MONGODB_URI in backend/.env to run this test.")
        return

    analysis_id = "test-analysis-verify"
    
    # Load detections or use realistic sample
    det_path = backend_dir / "results" / f"{analysis_id}_detections.json"
    if det_path.exists():
        with open(det_path, "r") as f:
            detections = json.load(f)
    else:
        detections = [
            {
                "frame": 10,
                "timestamp": 1.0,
                "object": "person",
                "confidence": 0.92,
                "track_id": 1,
                "attributes": "person wearing dark jacket",
                "is_threat": False,
                "threat_category": "NONE",
                "bounding_box": {"x1": 50, "y1": 50, "x2": 150, "y2": 250}
            },
            {
                "frame": 15,
                "timestamp": 1.5,
                "object": "knife",
                "confidence": 0.88,
                "track_id": None,
                "attributes": "silver blade knife",
                "is_threat": True,
                "threat_category": "LETHAL_WEAPON",
                "bounding_box": {"x1": 80, "y1": 120, "x2": 110, "y2": 160}
            }
        ]

    threat_analysis = {
        "overall_threat_level": "HIGH",
        "max_threat_score": 0.85,
        "total_incidents": 1,
        "incidents": []
    }
        
    object_counts = {}
    for d in detections:
        obj = d["object"]
        object_counts[obj] = object_counts.get(obj, 0) + 1
        
    result = {
        "detections": detections,
        "threat_analysis": threat_analysis,
        "object_counts": object_counts,
        "total_detections": len(detections)
    }
    
    filename = "test_video.mp4"
    
    # Persist
    _persist_to_mongodb(analysis_id, filename, result)
    
    collections = [
        "cases", 
        "detection_results", 
        "persons", 
        "evidence", 
        "investigations", 
        "investigation_reports"
    ]
    
    print("\n=== DOCUMENT COUNTS ===")
    for coll in collections:
        if coll == "cases":
            count = db[coll].count_documents({})
        else:
            count = db[coll].count_documents({"analysis_id": analysis_id})
        print(f"{coll}: {count}")
        
    # Sample documents
    print("\n=== SAMPLE: detection_results ===")
    sample_dr = db["detection_results"].find_one({"analysis_id": analysis_id})
    if sample_dr:
        sample_dr.pop('_id', None)
        print(json.dumps(sample_dr, indent=2))
        
    print("\n=== SAMPLE: investigation_reports ===")
    sample_ir = db["investigation_reports"].find_one({"analysis_id": analysis_id})
    if sample_ir:
        sample_ir.pop('_id', None)
        print(json.dumps(sample_ir, indent=2))

if __name__ == "__main__":
    run_verification()
