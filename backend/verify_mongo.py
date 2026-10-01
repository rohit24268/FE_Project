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
    analysis_id = "99c2421d-0b87-43ba-a90e-4ca326c81cda"
    
    # Load detections
    det_path = backend_dir / "results" / f"{analysis_id}_detections.json"
    with open(det_path, "r") as f:
        detections = json.load(f)
        
    # Load threats
    threat_path = backend_dir / "results" / f"{analysis_id}_threats.json"
    with open(threat_path, "r") as f:
        threat_analysis = json.load(f)
        
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
    
    # Verify counts
    db = get_db()
    
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
