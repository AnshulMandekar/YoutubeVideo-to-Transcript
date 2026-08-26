"""
MongoDB connection and CRUD operations using Motor (async driver).
"""
import os
from datetime import datetime, timezone
from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME", "lecture_notes")

client: Optional[AsyncIOMotorClient] = None
db = None


async def connect_db():
    """Initialize MongoDB connection and create indexes."""
    global client, db
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[MONGODB_DB_NAME]

    # Create text index for full-text search
    await db.videos.create_index(
        [
            ("title", "text"),
            ("channel", "text"),
            ("notes.summary", "text"),
            ("notes.sections.heading", "text"),
            ("notes.sections.subpoints", "text"),
            ("notes.key_takeaways", "text"),
            ("tags", "text"),
        ],
        name="video_text_search",
    )
    # Unique index on video_id to prevent duplicates
    await db.videos.create_index("video_id", unique=True, sparse=True)

    print(f"Connected to MongoDB: {MONGODB_DB_NAME}")


async def close_db():
    """Close MongoDB connection."""
    global client
    if client:
        client.close()
        print("MongoDB connection closed.")


def _serialize_doc(doc: dict) -> dict:
    """Convert MongoDB document to JSON-serializable dict."""
    if doc and "_id" in doc:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
    return doc


# ── CRUD Operations ──────────────────────────────────────────────────────────


async def create_video(video_data: dict) -> dict:
    """Insert a new video document. Returns the created document."""
    video_data["created_at"] = datetime.now(timezone.utc)
    video_data["updated_at"] = datetime.now(timezone.utc)
    result = await db.videos.insert_one(video_data)
    video_data["_id"] = result.inserted_id
    return _serialize_doc(video_data)


async def get_video_by_id(video_id: str) -> Optional[dict]:
    """Get a video document by its MongoDB _id."""
    doc = await db.videos.find_one({"_id": ObjectId(video_id)})
    return _serialize_doc(doc) if doc else None


async def get_video_by_video_id(yt_video_id: str) -> Optional[dict]:
    """Get a video document by its YouTube video ID (for duplicate detection)."""
    doc = await db.videos.find_one({"video_id": yt_video_id})
    return _serialize_doc(doc) if doc else None


async def update_video(video_id: str, update_data: dict) -> Optional[dict]:
    """Update a video document by its MongoDB _id."""
    update_data["updated_at"] = datetime.now(timezone.utc)
    await db.videos.update_one(
        {"_id": ObjectId(video_id)},
        {"$set": update_data},
    )
    return await get_video_by_id(video_id)


async def delete_video(video_id: str) -> bool:
    """Delete a video document by its MongoDB _id."""
    result = await db.videos.delete_one({"_id": ObjectId(video_id)})
    return result.deleted_count > 0


async def list_videos(
    query: Optional[str] = None,
    tag: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> list[dict]:
    """
    List videos with optional text search and tag filtering.
    Returns newest first.
    """
    filter_doc = {}

    if query:
        filter_doc["$text"] = {"$search": query}

    if tag:
        filter_doc["tags"] = tag

    cursor = (
        db.videos.find(filter_doc, {"notes": 0, "flowchart": 0, "transcript": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )

    docs = []
    async for doc in cursor:
        docs.append(_serialize_doc(doc))
    return docs


async def get_all_tags() -> list[str]:
    """Get all unique tags across all videos."""
    tags = await db.videos.distinct("tags")
    return sorted([t for t in tags if t])
