"""
Video metadata extraction using yt-dlp.
Lightweight — only fetches metadata, no video download.
"""
import yt_dlp
from typing import Optional


def format_duration(seconds: Optional[int]) -> Optional[str]:
    """Convert seconds to human-readable duration string."""
    if seconds is None:
        return None
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def fetch_metadata(video_id: str) -> dict:
    """
    Fetch video metadata using yt-dlp.

    Returns dict with: title, channel, thumbnail_url, duration, duration_seconds
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        duration_secs = info.get("duration")

        return {
            "title": info.get("title", "Untitled Video"),
            "channel": info.get("uploader") or info.get("channel", "Unknown Channel"),
            "thumbnail_url": info.get("thumbnail", ""),
            "duration": format_duration(duration_secs),
            "duration_seconds": duration_secs,
        }
    except Exception as e:
        # Return partial data on failure — title/channel can be populated later
        print(f"Warning: metadata extraction failed: {e}")
        return {
            "title": "Untitled Video",
            "channel": "Unknown Channel",
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            "duration": None,
            "duration_seconds": None,
        }
