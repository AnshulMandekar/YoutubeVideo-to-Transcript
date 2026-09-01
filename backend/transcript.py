"""
YouTube transcript extraction with multi-level fallback:
1. YouTube Transcript API (manual and auto-generated captions in any language with translation).
2. Audio-to-Transcript Fallback (downloads audio via yt-dlp and transcribes via Gemini 2.5 Flash).
"""
import os
import re
import json
import tempfile
from urllib.parse import urlparse, parse_qs
from typing import Optional, Callable

from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
from google import genai
from dotenv import load_dotenv

load_dotenv()


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


def parse_timestamp_to_seconds(ts_str: str) -> float:
    """Parse 'MM:SS' or 'HH:MM:SS' string to seconds."""
    parts = ts_str.strip().split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 1:
        return float(parts[0])
    return 0.0


def _fetch_from_youtube_api(video_id: str) -> dict:
    """
    Fetch transcript using YouTube Transcript API.
    Supports manual captions, auto-generated captions, and translations.
    """
    ytt_api = YouTubeTranscriptApi()
    transcript_list = ytt_api.list(video_id)

    preferred_languages = ["en", "en-US", "en-GB", "en-CA", "en-IN", "en-AU"]

    selected_transcript = None

    # 1. Try manual transcript in preferred languages
    try:
        selected_transcript = transcript_list.find_manually_created_transcript(preferred_languages)
    except Exception:
        pass

    # 2. Try auto-generated transcript in preferred languages
    if not selected_transcript:
        try:
            selected_transcript = transcript_list.find_generated_transcript(preferred_languages)
        except Exception:
            pass

    # 3. Try any transcript translated to English if available
    if not selected_transcript:
        for t in transcript_list:
            if t.is_translatable:
                try:
                    selected_transcript = t.translate("en")
                    break
                except Exception:
                    continue

    # 4. Fallback to any available transcript
    if not selected_transcript:
        try:
            selected_transcript = next(iter(transcript_list))
        except StopIteration:
            raise ValueError("No transcript streams available via YouTube API")

    raw_entries = selected_transcript.fetch()
    segments = []
    for entry in raw_entries:
        # Support dict format or object with attributes
        if isinstance(entry, dict):
            text = entry.get("text", "")
            start = float(entry.get("start", 0))
            duration = float(entry.get("duration", 0))
        else:
            text = getattr(entry, "text", "")
            start = float(getattr(entry, "start", 0))
            duration = float(getattr(entry, "duration", 0))

        if text:
            segments.append({
                "text": text,
                "start": start,
                "duration": duration,
            })

    if not segments:
        raise ValueError("YouTube transcript is empty")

    full_text = ""
    for seg in segments:
        ts = format_timestamp(seg["start"])
        full_text += f"[{ts}] {seg['text']}\n"

    last_seg = segments[-1]
    duration_seconds = last_seg["start"] + last_seg["duration"]

    return {
        "text": full_text,
        "segments": segments,
        "duration_seconds": duration_seconds,
        "source": "youtube_captions",
    }


def transcribe_audio_fallback(video_id: str) -> dict:
    """
    Download audio track using yt-dlp and transcribe using Gemini 2.5 Flash.
    Used when a YouTube video has no captions or transcripts disabled.
    """
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        raise ValueError(
            "Video has no captions and GEMINI_API_KEY is not configured for audio transcription fallback."
        )

    client = genai.Client(api_key=gemini_api_key)
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_template = os.path.join(tmpdir, "audio.%(ext)s")
        ydl_opts = {
            "format": "ba[ext=m4a]/ba/bestaudio",
            "outtmpl": audio_template,
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
        except Exception as e:
            raise ValueError(f"Failed to download video audio stream: {str(e)}")

        downloaded_files = [
            f for f in os.listdir(tmpdir)
            if os.path.isfile(os.path.join(tmpdir, f))
        ]
        if not downloaded_files:
            raise ValueError("Failed to extract audio track from video.")

        audio_path = os.path.join(tmpdir, downloaded_files[0])

        uploaded_file = None
        try:
            # Upload audio file to Gemini Files API
            uploaded_file = client.files.upload(file=audio_path)

            prompt = (
                "You are an expert audio transcription system. Transcribe the spoken audio in this file "
                "with accurate timestamps.\n\n"
                "Return a JSON array of segment objects in this exact format:\n"
                "[\n"
                "  {\"start\": 0.0, \"duration\": 4.5, \"text\": \"spoken text\"},\n"
                "  {\"start\": 4.5, \"duration\": 5.0, \"text\": \"spoken text\"}\n"
                "]\n\n"
                "Rules:\n"
                "1. Divide the speech into natural sentences or phrases with start time in seconds.\n"
                "2. Provide accurate, clean transcript text without hallucinations.\n"
                "3. Output ONLY the JSON array (no extra commentary or explanation)."
            )

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[uploaded_file, prompt],
            )

            raw_text = response.text.strip()
            # Clean markdown fences if present
            if raw_text.startswith("```"):
                first_nl = raw_text.find("\n")
                last_fence = raw_text.rfind("```")
                if last_fence > first_nl:
                    raw_text = raw_text[first_nl + 1 : last_fence].strip()
                else:
                    raw_text = raw_text[first_nl + 1 :].strip()

            segments = []
            try:
                parsed = json.loads(raw_text)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and "text" in item:
                            start = float(item.get("start", 0))
                            dur = float(item.get("duration", 0))
                            segments.append({
                                "text": str(item["text"]).strip(),
                                "start": start,
                                "duration": dur,
                            })
            except Exception:
                # If JSON parsing fails, check if formatted as [MM:SS] text
                lines = raw_text.splitlines()
                for line in lines:
                    line = line.strip()
                    match = re.match(r"^\[(\d{1,2}:\d{2}(?::\d{2})?)\]\s*(.+)$", line)
                    if match:
                        ts_str, text_val = match.groups()
                        start_sec = parse_timestamp_to_seconds(ts_str)
                        segments.append({
                            "text": text_val.strip(),
                            "start": start_sec,
                            "duration": 5.0,
                        })

            if not segments:
                # Fallback: create a single segment from full response text
                cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()
                if cleaned_text:
                    segments = [{
                        "text": cleaned_text,
                        "start": 0.0,
                        "duration": 0.0,
                    }]
                else:
                    raise ValueError("Audio transcription yielded empty text.")

            # Build full timestamped text
            full_text = ""
            for seg in segments:
                ts = format_timestamp(seg["start"])
                full_text += f"[{ts}] {seg['text']}\n"

            last_seg = segments[-1]
            duration_seconds = last_seg["start"] + last_seg.get("duration", 0)

            return {
                "text": full_text,
                "segments": segments,
                "duration_seconds": duration_seconds,
                "source": "gemini_audio_transcription",
            }

        finally:
            if uploaded_file and hasattr(uploaded_file, "name"):
                try:
                    client.files.delete(name=uploaded_file.name)
                except Exception:
                    pass


def fetch_transcript(video_id: str, on_fallback: Optional[Callable[[], None]] = None) -> dict:
    """
    Fetch transcript for a YouTube video.
    First tries YouTube captions (manual and auto-generated).
    If unavailable, automatically falls back to audio download & Gemini transcription.

    Returns:
        dict with keys:
            - 'text': Full transcript as a single string
            - 'segments': List of {text, start, duration} segments
            - 'duration_seconds': Total video duration based on last segment
            - 'source': 'youtube_captions' or 'gemini_audio_transcription'

    Raises:
        ValueError: If video ID is invalid or transcription fails
    """
    if not video_id:
        raise ValueError("Invalid video ID")

    # 1. Try YouTube Captions API first (Fast & Free)
    try:
        return _fetch_from_youtube_api(video_id)
    except Exception as yt_err:
        print(f"YouTube captions unavailable for {video_id} ({yt_err}). Falling back to audio transcription...")

        if on_fallback:
            try:
                on_fallback()
            except Exception:
                pass

        # 2. Fallback to downloading audio & AI transcription
        try:
            return transcribe_audio_fallback(video_id)
        except Exception as audio_err:
            raise ValueError(
                f"Could not retrieve transcript from YouTube captions ({str(yt_err)}) "
                f"and audio fallback transcription failed: {str(audio_err)}"
            )


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
