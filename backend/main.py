"""
FastAPI application — main entry point with all API routes.
"""
import os
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from typing import Optional

from database import connect_db, close_db, create_video, get_video_by_id, get_video_by_video_id, update_video, delete_video, list_videos, get_all_tags
from models import VideoCreate, ProcessingStatus
from transcript import extract_video_id, fetch_transcript
from metadata import fetch_metadata
from llm import generate_notes, generate_flowchart


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    await connect_db()
    yield
    await close_db()


app = FastAPI(
    title="YouTube Lecture Notes API",
    description="Convert YouTube videos into structured lecture notes with flowcharts",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend (configurable for production via FRONTEND_URL env var)
allowed_origins = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8000",
]
frontend_url = os.getenv("FRONTEND_URL")
if frontend_url:
    allowed_origins.append(frontend_url)
else:
    # If no FRONTEND_URL set, allow all origins (development mode)
    allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health Check ─────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "lecture-notes-api"}


# ── Video Endpoints ──────────────────────────────────────────────────────────


@app.post("/api/videos")
async def create_video_endpoint(payload: VideoCreate):
    """
    Submit a YouTube URL for processing.
    Full pipeline: validate → metadata → transcript → notes → flowchart.
    """
    url = payload.url.strip()

    # 1. Validate URL and extract video ID
    video_id = extract_video_id(url)
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL. Please provide a valid YouTube video link.")

    # 2. Check for duplicates
    existing = await get_video_by_video_id(video_id)
    if existing:
        return existing

    # 3. Create initial document
    video_doc = await create_video({
        "url": url,
        "video_id": video_id,
        "status": ProcessingStatus.PENDING,
        "title": None,
        "channel": None,
        "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
        "duration": None,
        "duration_seconds": None,
        "notes": None,
        "flowchart": None,
        "transcript": None,
        "tags": [],
        "error_message": None,
    })

    doc_id = video_doc["id"]

    try:
        # 4. Fetch metadata
        await update_video(doc_id, {"status": ProcessingStatus.FETCHING_METADATA})
        meta = fetch_metadata(video_id)
        await update_video(doc_id, {
            "title": meta["title"],
            "channel": meta["channel"],
            "thumbnail_url": meta["thumbnail_url"],
            "duration": meta["duration"],
            "duration_seconds": meta.get("duration_seconds"),
        })

        # 5. Fetch transcript
        await update_video(doc_id, {"status": ProcessingStatus.FETCHING_TRANSCRIPT})
        transcript_data = fetch_transcript(video_id)
        transcript_text = transcript_data["text"]
        await update_video(doc_id, {"transcript": transcript_text})

        # 6. Generate notes via LLM
        await update_video(doc_id, {"status": ProcessingStatus.GENERATING_NOTES})
        notes = await generate_notes(transcript_text)

        # Extract tags from notes if present
        tags = notes.pop("tags", [])
        await update_video(doc_id, {"notes": notes, "tags": tags})

        # 7. Generate flowchart via LLM
        await update_video(doc_id, {"status": ProcessingStatus.GENERATING_FLOWCHART})
        flowchart = await generate_flowchart(notes)
        await update_video(doc_id, {"flowchart": flowchart})

        # 8. Mark as done
        final_doc = await update_video(doc_id, {"status": ProcessingStatus.DONE})
        return final_doc

    except ValueError as e:
        # Known errors (transcript unavailable, etc.)
        await update_video(doc_id, {
            "status": ProcessingStatus.FAILED,
            "error_message": str(e),
        })
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        # Unexpected errors
        tb = traceback.format_exc()
        print(f"Pipeline error for {video_id}: {tb}")
        await update_video(doc_id, {
            "status": ProcessingStatus.FAILED,
            "error_message": f"Processing failed: {str(e)}",
        })
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.get("/api/videos")
async def list_videos_endpoint(
    q: Optional[str] = Query(None, description="Search query"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """List all processed videos with optional search and tag filtering."""
    videos = await list_videos(query=q, tag=tag, skip=skip, limit=limit)
    return {"videos": videos, "count": len(videos)}


@app.get("/api/videos/{video_id}")
async def get_video_endpoint(video_id: str):
    """Get full video details including notes and flowchart."""
    video = await get_video_by_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@app.delete("/api/videos/{video_id}")
async def delete_video_endpoint(video_id: str):
    """Delete a video and its associated data."""
    deleted = await delete_video(video_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Video not found")
    return {"message": "Video deleted successfully"}


@app.get("/api/videos/{video_id}/export/markdown")
async def export_markdown_endpoint(video_id: str):
    """Export video notes as a Markdown document."""
    video = await get_video_by_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    notes = video.get("notes")
    if not notes:
        raise HTTPException(status_code=404, detail="No notes available for this video")

    # Build Markdown
    md_lines = []
    md_lines.append(f"# {notes.get('title', video.get('title', 'Lecture Notes'))}\n")
    md_lines.append(f"**Source:** [{video.get('title', 'YouTube Video')}]({video.get('url', '')})\n")
    md_lines.append(f"**Channel:** {video.get('channel', 'Unknown')}\n")
    if video.get("duration"):
        md_lines.append(f"**Duration:** {video['duration']}\n")
    md_lines.append(f"\n## Summary\n\n{notes.get('summary', '')}\n")

    md_lines.append("\n---\n")

    for section in notes.get("sections", []):
        timestamp = section.get("timestamp", "")
        heading = section.get("heading", "")
        ts_str = f" [{timestamp}]" if timestamp else ""
        md_lines.append(f"\n## {heading}{ts_str}\n")

        for point in section.get("subpoints", []):
            md_lines.append(f"- {point}")

        if section.get("key_terms"):
            md_lines.append(f"\n**Key Terms:** {', '.join(section['key_terms'])}\n")

    if notes.get("key_takeaways"):
        md_lines.append("\n---\n\n## Key Takeaways\n")
        for takeaway in notes["key_takeaways"]:
            md_lines.append(f"- {takeaway}")

    # Add flowchart if available
    flowchart = video.get("flowchart")
    if flowchart:
        md_lines.append("\n---\n\n## Concept Map\n")
        md_lines.append(f"```mermaid\n{flowchart}\n```\n")

    markdown = "\n".join(md_lines)

    return PlainTextResponse(
        content=markdown,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="{video.get("video_id", "notes")}_notes.md"'
        },
    )


@app.get("/api/tags")
async def get_tags_endpoint():
    """Get all unique tags for filtering."""
    tags = await get_all_tags()
    return {"tags": tags}
