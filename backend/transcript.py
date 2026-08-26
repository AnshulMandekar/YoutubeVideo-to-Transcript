"""
YouTube transcript extraction using youtube-transcript-api.
Handles URL parsing, transcript fetching, and chunking for long videos.
"""
import re
from urllib.parse import urlparse, parse_qs
from typing import Optional

from youtube_transcript_api import YouTubeTranscriptApi


def extract_video_id(url: str) -> Optional[str]:
    """
    Extract YouTube video ID from various URL formats:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://www.youtube.com/shorts/VIDEO_ID
    """
    url = url.strip()

    # Direct video ID (11 chars)
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url):
        return url

    parsed = urlparse(url)

    # youtu.be/VIDEO_ID
    if parsed.hostname in ("youtu.be",):
        return parsed.path.lstrip("/").split("/")[0] or None

    # youtube.com/watch?v=VIDEO_ID
    if parsed.hostname in ("www.youtube.com", "youtube.com", "m.youtube.com"):
        if parsed.path == "/watch":
            qs = parse_qs(parsed.query)
            return qs.get("v", [None])[0]
        # /embed/VIDEO_ID or /shorts/VIDEO_ID or /v/VIDEO_ID
        for prefix in ("/embed/", "/shorts/", "/v/"):
            if parsed.path.startswith(prefix):
                return parsed.path[len(prefix):].split("/")[0] or None

    return None


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS or MM:SS format."""
    total_seconds = int(seconds)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def fetch_transcript(video_id: str) -> dict:
    """
    Fetch transcript for a YouTube video.

    Returns:
        dict with keys:
            - 'text': Full transcript as a single string
            - 'segments': List of {text, start, duration} segments
            - 'language': Language code of the transcript
            - 'duration_seconds': Total video duration based on last segment

    Raises:
        ValueError: If video ID is invalid or transcript unavailable
    """
    if not video_id:
        raise ValueError("Invalid video ID")

    try:
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.fetch(video_id)

        segments = []
        for entry in transcript_list:
            segments.append({
                "text": entry.text,
                "start": entry.start,
                "duration": entry.duration,
            })

        if not segments:
            raise ValueError("Transcript is empty")

        # Build full text with timestamps
        full_text = ""
        for seg in segments:
            ts = format_timestamp(seg["start"])
            full_text += f"[{ts}] {seg['text']}\n"

        # Estimate total duration from last segment
        last_seg = segments[-1]
        duration_seconds = last_seg["start"] + last_seg["duration"]

        return {
            "text": full_text,
            "segments": segments,
            "duration_seconds": duration_seconds,
        }

    except Exception as e:
        err_msg = str(e).lower()
        if "disabled" in err_msg:
            raise ValueError(
                "Transcripts are disabled for this video. The video owner has turned off captions."
            )
        elif "no transcript" in err_msg or "not found" in err_msg or "could not retrieve" in err_msg:
            raise ValueError(
                "No transcript found for this video. It may not have auto-generated or manual captions."
            )
        elif "unavailable" in err_msg or "private" in err_msg:
            raise ValueError(
                "This video is unavailable. It may be private, deleted, or age-restricted."
            )
        else:
            raise ValueError(f"Failed to fetch transcript: {str(e)}")


def chunk_transcript(
    full_text: str, max_chunk_chars: int = 30000, overlap_chars: int = 500
) -> list[str]:
    """
    Split a long transcript into overlapping chunks for batch LLM processing.
    Each chunk is roughly max_chunk_chars characters, with overlap_chars of overlap
    to preserve context at boundaries.

    Returns a list of transcript chunks.
    """
    if len(full_text) <= max_chunk_chars:
        return [full_text]

    chunks = []
    start = 0
    while start < len(full_text):
        end = start + max_chunk_chars

        # Try to break at a newline for clean boundaries
        if end < len(full_text):
            newline_pos = full_text.rfind("\n", start + max_chunk_chars - 1000, end)
            if newline_pos > start:
                end = newline_pos + 1

        chunks.append(full_text[start:end])
        start = end - overlap_chars

    return chunks
