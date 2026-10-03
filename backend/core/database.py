"""
MongoDB connection module for ForenSight AI.

Reads configuration from environment variables:
  MONGODB_URI       — MongoDB connection string (Atlas or local)
  MONGODB_DATABASE  — Database name (default: ForenSightAI)

Usage:
    from core.database import get_db
    db = get_db()
    db["cases"].find_one(...)
"""

import os
import sys

from pymongo import MongoClient, ASCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError


# --------------------------------------------------
# MODULE-LEVEL SINGLETON
# --------------------------------------------------

_client: MongoClient | None = None
_db = None
_initialized = False


def _connect():
    """
    Establishes the MongoDB connection once.
    Called lazily on first get_db() / get_client() call.
    """
    global _client, _db, _initialized

    if _initialized:
        return

    _initialized = True

    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DATABASE", "ForenSightAI")

    if not uri:
        print(
            "[MongoDB] WARNING: MONGODB_URI is not set in environment. "
            "MongoDB features will be unavailable. "
            "Set MONGODB_URI in backend/.env to enable.",
            file=sys.stderr,
        )
        return

    try:
        _client = MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
        )

        # Force a connection check (lightweight ping)
        _client.admin.command("ping")

        _db = _client[db_name]

        print(f"[MongoDB] Connected successfully")
        print(f"[MongoDB] Database: {db_name}")

        # Create indexes on first connection
        _ensure_indexes()

    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        print(
            f"[MongoDB] ERROR: Could not connect to MongoDB — {e}\n"
            f"[MongoDB] The application will continue without MongoDB. "
            f"JSON fallback will be used where available.",
            file=sys.stderr,
        )
        _client = None
        _db = None

    except Exception as e:
        print(
            f"[MongoDB] ERROR: Unexpected error during connection — {e}",
            file=sys.stderr,
        )
        _client = None
        _db = None


def _ensure_indexes():
    """Create sensible indexes for frequently queried fields."""
    if _db is None:
        return

    try:
        # Cases
        _db["cases"].create_index(
            [("case_id", ASCENDING)],
            unique=True,
            background=True,
        )

        # Detection results (per-detection)
        _db["detection_results"].create_index(
            [("analysis_id", ASCENDING)],
            background=True,
        )
        _db["detection_results"].create_index(
            [("analysis_id", ASCENDING), ("track_id", ASCENDING)],
            background=True,
        )

        # Evidence (individual evidence records)
        _db["evidence"].create_index(
            [("analysis_id", ASCENDING)],
            background=True,
        )

        # Persons
        _db["persons"].create_index(
            [("analysis_id", ASCENDING)],
            background=True,
        )

        # Investigations
        _db["investigations"].create_index(
            [("analysis_id", ASCENDING)],
            background=True,
        )
        _db["investigations"].create_index(
            [("case_id", ASCENDING)],
            background=True,
        )

        # Investigation Reports
        _db["investigation_reports"].create_index(
            [("analysis_id", ASCENDING)],
            background=True,
        )

        print("[MongoDB] Indexes verified")

    except Exception as e:
        print(f"[MongoDB] WARNING: Index creation failed — {e}")


def get_db():
    """
    Returns the MongoDB database instance.
    Returns None if MongoDB is not configured or unreachable.
    """
    if not _initialized:
        _connect()
    return _db


def get_client() -> MongoClient | None:
    """
    Returns the raw MongoClient instance.
    Returns None if MongoDB is not configured or unreachable.
    """
    if not _initialized:
        _connect()
    return _client


def is_connected() -> bool:
    """Returns True if MongoDB is connected and responsive."""
    try:
        client = get_client()
        if client is None:
            return False
        client.admin.command("ping")
        return True
    except Exception:
        return False
