import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from pymongo import ReturnDocument

def create_case_record(
    db,
    title: str | None = None,
    description: str = "",
    investigator: str = "",
    status: str = "open",
    analysis_id: str | None = None,
) -> dict:
    """Create a numbered case and its dedicated MongoDB collection."""
    counter = db["cases"].find_one_and_update(
        {"_id": "case_sequence"},
        {"$inc": {"next_number": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    collection_name = f"case{counter['next_number']}"
    case_title = title.strip() if title and title.strip() else f"Case {counter['next_number']}"
    case = {
        "case_id": str(uuid.uuid4()),
        "case_number": counter["next_number"],
        "storage_collection": collection_name,
        "title": case_title,
        "case_name": case_title,
        "description": description.strip(),
        "investigator": investigator.strip(),
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis_ids": [analysis_id] if analysis_id else [],
    }

    try:
        db.create_collection(collection_name)
        db["cases"].insert_one(case.copy())
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to create MongoDB storage for case: {e}",
        ) from e

    return case


def get_case_collection_name(db, case_id: str) -> str:
    """Return a stored case collection name, including safe legacy names."""
    case = db["cases"].find_one({"case_id": case_id}, {"storage_collection": 1})
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    collection_name = case.get("storage_collection")
    if collection_name and (
        collection_name.startswith("case_")
        or (
            collection_name.startswith("case")
            and collection_name[4:].isdigit()
        )
    ):
        return collection_name

    try:
        return f"case_{uuid.UUID(case_id).hex}"
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid case ID") from e
