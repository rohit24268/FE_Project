from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from core.database import get_db

router = APIRouter(tags=["Persons Search"])

@router.get("/search-persons")
def search_persons(
    analysis_id: Optional[str] = None,
    case_id: Optional[str] = None,
    track_id: Optional[int] = None,
    attributes: Optional[str] = None,
    min_detection_count: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100)
):
    """
    Search and filter tracked persons across analyses and cases.
    
    Multiple filters combine with AND semantics.
    If no filters are provided, it returns a paginated list of all persons.
    
    CRITICAL NOTE ON TRACK ID:
    track_id is a within-video tracking identifier, not identity.
    It is scoped to a single analysis/video session. 
    The same real person could get different track_ids across different videos.
    This is not facial recognition and does not establish real-world identity.
    """
    db = get_db()
    if db is None:
        raise HTTPException(status_code=503, detail="Database connection not available")

    query = {}
    
    if analysis_id:
        query["analysis_id"] = analysis_id
    if case_id:
        query["case_id"] = case_id
    if track_id is not None:
        query["track_id"] = track_id
        
    if attributes:
        # Regex search on the text field since it's just a generated string
        query["attributes"] = {"$regex": attributes, "$options": "i"}
        
    if min_detection_count is not None:
        query["detection_count"] = {"$gte": min_detection_count}
        
    try:
        total_count = db["persons"].count_documents(query)
        
        skip = (page - 1) * page_size
        cursor = db["persons"].find(query, {"_id": 0}).skip(skip).limit(page_size).sort("first_seen", 1)
        results = list(cursor)
        
        return {
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "filters_applied": {
                "analysis_id": analysis_id,
                "case_id": case_id,
                "track_id": track_id,
                "attributes": attributes,
                "min_detection_count": min_detection_count
            },
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
