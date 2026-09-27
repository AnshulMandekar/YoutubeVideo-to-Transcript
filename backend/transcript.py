"""
YouTube transcript extraction. Every video ends up with a timestamped ENGLISH transcript:

1. YouTube captions (manual or auto-generated, in any language). Captions that are not in
   English (e.g. Hindi / Hinglish) are translated to English with Gemini.
2. No captions -> Gemini watches the public YouTube URL directly and transcribes it into
   English. Nothing is downloaded, so this also works on cloud hosts where YouTube blocks
   downloads.
3. Last resort -> download the audio with yt-dlp, upload it to Gemini and transcribe it
   into English.
"""
import os
import re
import math
import time
import tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs
from typing import Optional, Callable

from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
from google import genai
from google.genai import types, errors
from dotenv import load_dotenv

load_dotenv()

GEMINI_MODEL = "gemini-2.5-flash"

# Long videos are transcribed in windows so timestamps stay accurate and each response stays
# far below the model's output-token limit.
YOUTUBE_WINDOW_SECONDS = 15 * 60
# The whole audio file is sent with every window request, so use fewer, larger windows.
AUDIO_WINDOW_SECONDS = 30 * 60
# Frames sampled per second when Gemini watches a video. Speech is what matters; a few
# frames still let it read slides and board work to spell technical terms correctly.
YOUTUBE_FPS = 0.2

# Auto-generated captions arrive as ~5 second fragments. Grouping them into blocks before
# translating gives the model whole sentences to work with.
TRANSLATION_BLOCK_SECONDS = 20
TRANSLATION_CHUNK_CHARS = 10000


TRANSCRIBE_PROMPT = """You are a professional transcriber and translator. {scope}

Write the transcript in ENGLISH:
- If the speaker uses Hindi, Hinglish or any other language, translate what is said into clear, natural English. Keep technical terms, names, formulas and code exactly as spoken.
- Do not summarize or skip anything, and do not add anything that is not said.
- Ignore music and background noise. If nobody speaks, output only the LANGUAGE line.

Output format: the first line names the language that is spoken, then one line per sentence or short phrase, each starting with the time it is spoken, measured from the start of the full video:
LANGUAGE: <language name, e.g. Hindi>
[MM:SS] English text
[MM:SS] English text
Use [H:MM:SS] after the first hour. Output nothing else."""


TRANSLATE_PROMPT = """Translate this YouTube lecture transcript into clear, natural English. It was captioned automatically in {language}, so it may be Hinglish (Hindi mixed with English, often with English words written in Devanagari) and may contain speech-recognition errors.

Rules:
- Keep every line and its [timestamp] exactly as given; translate only the text after the timestamp.
- Translate faithfully. Do not summarize, skip or add content. Fix obvious recognition errors from context.
- Keep technical terms, names, formulas and code in their standard English form.
- Output only the translated lines.

TRANSCRIPT:
{transcript}"""


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


# ── Shared helpers ───────────────────────────────────────────────────────────


_TS = r"\d{1,2}(?::\d{2}){1,2}(?:\.\d+)?"
# "[12:34] text", "12:34 - text" or "[12:34 - 12:40] text"
_LINE_RE = re.compile(rf"^\[?\s*({_TS})\s*(?:[-–]\s*{_TS}\s*)?\]?\s*[-–:]?\s*(.*)$")
_LANGUAGE_RE = re.compile(r"^[*_\s]*language[*_\s]*:\s*(.+)$", re.IGNORECASE)


def _is_english(language_code: str) -> bool:
    return language_code.split("-")[0].lower() == "en"


def _parse_timestamped_lines(raw: str) -> tuple[Optional[str], list[dict]]:
    """Parse Gemini output ('LANGUAGE: x' then '[MM:SS] text' lines) into (language, segments)."""
    language = None
    segments = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("```"):
            continue
        lang_match = _LANGUAGE_RE.match(line)
        if lang_match and not segments:
            language = lang_match.group(1).strip(" *_.") or None
            continue
        match = _LINE_RE.match(line)
        if match:
            text = match.group(2).strip()
            if text:
                segments.append({
                    "text": text,
                    "start": parse_timestamp_to_seconds(match.group(1)),
                    "duration": 0.0,
                })
        elif segments:
            # Line without a timestamp: the model wrapped a long sentence.
            segments[-1]["text"] += " " + line
    return language, segments


def _build_result(segments: list[dict], source: str, language: Optional[str]) -> dict:
    """Sort segments, fill in missing durations and build the transcript result dict."""
    segments = sorted(segments, key=lambda s: s["start"])
    for current, following in zip(segments, segments[1:]):
        if not current["duration"]:
            current["duration"] = max(0.0, following["start"] - current["start"])
    if not segments[-1]["duration"]:
        segments[-1]["duration"] = 5.0

    full_text = "".join(f"[{format_timestamp(s['start'])}] {s['text']}\n" for s in segments)
    last_seg = segments[-1]

    return {
        "text": full_text,
        "segments": segments,
        "duration_seconds": last_seg["start"] + last_seg["duration"],
        "source": source,
        "language": language,
    }


def _gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY is not configured, so this video cannot be transcribed or translated."
        )
    return genai.Client(
        api_key=api_key,
        # Retries rate limits (429) and transient server errors with exponential backoff.
        http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=4)),
    )


def _generate(client: genai.Client, contents, media_resolution=None) -> str:
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            # Transcription and translation don't benefit from thinking; skip it for speed.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            media_resolution=media_resolution,
        ),
    )
    return response.text or ""


def _plan_windows(duration_seconds: Optional[float], window_seconds: int) -> list[tuple[float, Optional[float]]]:
    """Split a video into roughly equal (start, end) windows. end=None means 'the whole video'."""
    if not duration_seconds:
        return [(0.0, None)]
    count = max(1, round(duration_seconds / window_seconds))
    if count == 1:
        return [(0.0, None)]
    size = duration_seconds / count
    return [(i * size, (i + 1) * size) for i in range(count)]


def _transcribe_windows(
    windows: list[tuple[float, Optional[float]]],
    request: Callable[[float, Optional[float]], str],
    max_workers: int,
) -> tuple[Optional[str], list[dict]]:
    """
    Run one Gemini transcription request per window and stitch the results together.
    A failed window is skipped; if every window fails, the first error is raised.
    """

    def run(window):
        start, end = window
        try:
            language, segments = _parse_timestamped_lines(request(start, end))
        except Exception as e:
            print(f"Transcription failed for window starting at {format_timestamp(start)}: {e}")
            return None, [], e
        if end is None:
            return language, segments, None

        # Clips sometimes come back timed from the start of the clip, not the full video.
        if start > 0 and segments and segments[0]["start"] < start - 30 and segments[-1]["start"] <= end - start + 30:
            for seg in segments:
                seg["start"] += start
        # Drop anything outside the window (the audio fallback always sees the full file).
        in_window = [s for s in segments if start - 15 <= s["start"] <= end + 15]
        return language, in_window or segments, None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(run, windows))

    languages = [language for language, _, _ in results if language]
    segments = [seg for _, window_segments, _ in results for seg in window_segments]
    window_errors = [error for _, _, error in results if error]
    if not segments and window_errors:
        raise window_errors[0]
    return (languages[0] if languages else None), segments


# ── 1. YouTube captions ──────────────────────────────────────────────────────


def _fetch_youtube_captions(video_id: str) -> tuple[list[dict], str, str]:
    """
    Fetch the best caption track in any language.
    Returns (segments, language_code, language_name).
    """
    tracks = list(YouTubeTranscriptApi().list(video_id))
    if not tracks:
        raise ValueError("Video has no caption tracks")

    # English first, then any other language (translated later); manual beats auto-generated.
    tracks.sort(key=lambda t: (not _is_english(t.language_code), t.is_generated))
    track = tracks[0]

    segments = []
    for entry in track.fetch():
        text = entry.text.replace("\n", " ").strip()
        if text:
            segments.append({"text": text, "start": float(entry.start), "duration": float(entry.duration)})

    if not segments:
        raise ValueError("YouTube transcript is empty")

    language_name = track.language.replace("(auto-generated)", "").strip()
    return segments, track.language_code, language_name


def _translate_segments(segments: list[dict], language: str) -> tuple[list[dict], bool]:
    """
    Translate caption segments to English, keeping timestamps.
    Returns (segments, translated). Parts that fail to translate keep their original text.
    """
    client = _gemini_client()

    blocks = []
    for seg in segments:
        if blocks and seg["start"] - blocks[-1]["start"] < TRANSLATION_BLOCK_SECONDS:
            blocks[-1]["text"] += " " + seg["text"]
        else:
            blocks.append({"text": seg["text"], "start": seg["start"], "duration": 0.0})

    chunks, current, size = [], [], 0
    for block in blocks:
        if current and size + len(block["text"]) > TRANSLATION_CHUNK_CHARS:
            chunks.append(current)
            current, size = [], 0
        current.append(block)
        size += len(block["text"])
    if current:
        chunks.append(current)

    def translate(chunk):
        lines = "".join(f"[{format_timestamp(b['start'])}] {b['text']}\n" for b in chunk)
        try:
            raw = _generate(client, TRANSLATE_PROMPT.format(language=language, transcript=lines))
            _, translated = _parse_timestamped_lines(raw)
        except Exception as e:
            print(f"Translation failed for chunk starting at {format_timestamp(chunk[0]['start'])}: {e}")
            translated = []
        return translated or None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(translate, chunks))

    translated_any = any(results)
    merged = [seg for chunk, result in zip(chunks, results) for seg in (result or chunk)]
    return merged, translated_any


# ── 2. Gemini watches the YouTube video ──────────────────────────────────────


def _transcribe_from_youtube_url(client: genai.Client, video_id: str, duration_seconds: Optional[float]) -> dict:
    """Let Gemini fetch the public YouTube video itself and transcribe it into English."""
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    def request(start: float, end: Optional[float]) -> str:
        if end is None:
            scope = "Transcribe all of the speech in this video."
            clip = {}
        else:
            scope = (
                f"This is a clip from {format_timestamp(start)} to {format_timestamp(end)} of a longer "
                f"video. Transcribe all of the speech in the clip."
            )
            clip = {"start_offset": f"{int(start)}s", "end_offset": f"{math.ceil(end)}s"}

        def ask(fps: Optional[float]) -> str:
            metadata = {**clip, "fps": fps} if fps else clip
            part = types.Part(
                file_data=types.FileData(file_uri=video_url),
                video_metadata=types.VideoMetadata(**metadata) if metadata else None,
            )
            return _generate(
                client,
                [part, TRANSCRIBE_PROMPT.format(scope=scope)],
                media_resolution=types.MediaResolution.MEDIA_RESOLUTION_LOW,
            )

        try:
            return ask(YOUTUBE_FPS)
        except errors.ClientError as e:
            if e.code != 400:
                raise
            # Retry with the default frame rate in case custom sampling is rejected.
            return ask(None)

    windows = _plan_windows(duration_seconds, YOUTUBE_WINDOW_SECONDS)
    language, segments = _transcribe_windows(windows, request, max_workers=3)
    if not segments:
        raise ValueError("Gemini returned no speech for this video")
    return _build_result(segments, "gemini_youtube_transcription", language)


# ── 3. Download audio and transcribe it ──────────────────────────────────────


_AUDIO_MIME_TYPES = {
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".webm": "audio/webm",
    ".opus": "audio/ogg",
    ".ogg": "audio/ogg",
    ".mp3": "audio/mp3",
}


def _wait_until_active(client: genai.Client, uploaded, timeout_seconds: int = 300):
    """Uploaded files must finish processing before they can be used in a prompt."""
    deadline = time.monotonic() + timeout_seconds
    while uploaded.state == types.FileState.PROCESSING:
        if time.monotonic() > deadline:
            raise ValueError("Gemini took too long to process the uploaded audio.")
        time.sleep(3)
        uploaded = client.files.get(name=uploaded.name)
    if uploaded.state == types.FileState.FAILED:
        raise ValueError("Gemini could not process the uploaded audio.")
    return uploaded


def _transcribe_from_audio(client: genai.Client, video_id: str, duration_seconds: Optional[float]) -> dict:
    """Download the audio track with yt-dlp, upload it to Gemini and transcribe it into English."""
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    with tempfile.TemporaryDirectory() as tmpdir:
        ydl_opts = {
            "format": "ba[ext=m4a]/ba/bestaudio",
            "outtmpl": os.path.join(tmpdir, "audio.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            # YouTube needs a JS runtime for full format access; use whichever is installed.
            "js_runtimes": {"deno": {}, "node": {}},
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
        except Exception as e:
            raise ValueError(f"Failed to download video audio stream: {e}")

        duration_seconds = duration_seconds or (info or {}).get("duration")
        downloaded_files = [f for f in os.listdir(tmpdir) if os.path.isfile(os.path.join(tmpdir, f))]
        if not downloaded_files:
            raise ValueError("Failed to extract audio track from video.")
        audio_path = os.path.join(tmpdir, downloaded_files[0])
        mime_type = _AUDIO_MIME_TYPES.get(os.path.splitext(audio_path)[1].lower(), "audio/mp4")

        uploaded = client.files.upload(file=audio_path, config=types.UploadFileConfig(mime_type=mime_type))

    try:
        uploaded = _wait_until_active(client, uploaded)

        def request(start: float, end: Optional[float]) -> str:
            if end is None:
                scope = "Transcribe all of the speech in this audio recording of a video."
            else:
                scope = (
                    f"This is the audio of a video. Transcribe ONLY the speech between "
                    f"{format_timestamp(start)} and {format_timestamp(end)}."
                )
            return _generate(client, [uploaded, TRANSCRIBE_PROMPT.format(scope=scope)])

        windows = _plan_windows(duration_seconds, AUDIO_WINDOW_SECONDS)
        # Sequential: every window request carries the whole file, which adds up fast on rate limits.
        language, segments = _transcribe_windows(windows, request, max_workers=1)
        if not segments:
            raise ValueError("Audio transcription yielded empty text.")
        return _build_result(segments, "gemini_audio_transcription", language)
    finally:
        try:
            client.files.delete(name=uploaded.name)
        except Exception:
            pass


# ── Public API ───────────────────────────────────────────────────────────────


def fetch_transcript(
    video_id: str,
    duration_seconds: Optional[float] = None,
    on_fallback: Optional[Callable[[], None]] = None,
) -> dict:
    """
    Fetch an English transcript for a YouTube video, whether or not it has captions.

    Args:
        video_id: YouTube video ID.
        duration_seconds: Video length if known (from metadata); used to split long
            videos into windows when transcribing with Gemini.
        on_fallback: Called before falling back to Gemini transcription.

    Returns:
        dict with keys:
            - 'text': Full transcript, one '[MM:SS] text' line per segment
            - 'segments': List of {text, start, duration} segments
            - 'duration_seconds': Total duration based on last segment
            - 'source': 'youtube_captions', 'youtube_captions_translated',
              'gemini_youtube_transcription' or 'gemini_audio_transcription'
            - 'language': Spoken language of the video, if known

    Raises:
        ValueError: If video ID is invalid or every method fails
    """
    if not video_id:
        raise ValueError("Invalid video ID")

    # 1. YouTube captions (fast and free), translated to English when needed.
    try:
        segments, language_code, language = _fetch_youtube_captions(video_id)
    except Exception as caption_err:
        print(f"No usable YouTube captions for {video_id} ({type(caption_err).__name__}). Transcribing with Gemini...")
    else:
        if _is_english(language_code):
            return _build_result(segments, "youtube_captions", language)
        print(f"Captions for {video_id} are in {language}. Translating to English...")
        segments, translated = _translate_segments(segments, language)
        source = "youtube_captions_translated" if translated else "youtube_captions"
        return _build_result(segments, source, language)

    if on_fallback:
        try:
            on_fallback()
        except Exception:
            pass

    # 2 & 3. No captions: have Gemini watch the video, else download the audio.
    client = _gemini_client()
    failures = []
    for label, transcribe in (
        ("Gemini video transcription", _transcribe_from_youtube_url),
        ("audio download transcription", _transcribe_from_audio),
    ):
        try:
            return transcribe(client, video_id, duration_seconds)
        except Exception as e:
            print(f"{label} failed for {video_id}: {e}")
            failures.append(f"{label}: {e}")

    raise ValueError(
        "This video has no captions and it could not be transcribed. " + " | ".join(failures)
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
