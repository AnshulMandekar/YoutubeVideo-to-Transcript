"""
Pydantic models for request/response validation.
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    FETCHING_METADATA = "fetching_metadata"
    FETCHING_TRANSCRIPT = "fetching_transcript"
    GENERATING_NOTES = "generating_notes"
    GENERATING_FLOWCHART = "generating_flowchart"
    DONE = "done"
    FAILED = "failed"


# ── Request Models ───────────────────────────────────────────────────────────


class VideoCreate(BaseModel):
    url: str = Field(..., description="YouTube video URL")


# ── Note Structure Models ────────────────────────────────────────────────────


class NoteSection(BaseModel):
    heading: str
    timestamp: Optional[str] = None
    subpoints: list[str] = []
    key_terms: list[str] = []


class StructuredNotes(BaseModel):
    title: str
    summary: str
    sections: list[NoteSection] = []
    key_takeaways: list[str] = []


# ── Response Models ──────────────────────────────────────────────────────────


class VideoSummary(BaseModel):
    """Lightweight video object for dashboard listing."""
    id: str
    url: str
    video_id: str
    title: Optional[str] = None
    channel: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[str] = None
    status: ProcessingStatus
    tags: list[str] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VideoDetail(BaseModel):
    """Full video object with notes and flowchart."""
    id: str
    url: str
    video_id: str
    title: Optional[str] = None
    channel: Optional[str] = None
    thumbnail_url: Optional[str] = None
    duration: Optional[str] = None
    status: ProcessingStatus
    tags: list[str] = []
    notes: Optional[StructuredNotes] = None
    flowchart: Optional[str] = None
    transcript: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
