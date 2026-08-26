# YouTube-to-Lecture-Notes Web App — Detailed Project Spec

## 1. Overview

Build a web application where a user pastes a YouTube video link, and the system:
1. Extracts the video's transcript
2. Uses an LLM to convert the transcript into well-organized, structured lecture notes
3. Generates a flowchart/mind-map of the topics and their relationships
4. Stores the video link, notes, and flowchart in a database
5. Displays everything in a searchable, organized dashboard

## 2. Core Features

### 2.1 Video Input & Transcript Extraction
- User pastes a YouTube URL into an input field
- Backend validates the URL and extracts the video ID
- Backend fetches the transcript using one of:
  - YouTube's auto-generated captions (via `youtube-transcript-api` in Python, or `youtube-captions-scraper` in Node)
  - YouTube Data API (for metadata: title, channel, duration, thumbnail)
  - Fallback: if no captions exist, download audio and run speech-to-text (e.g., Whisper API) — flag this as slower/optional
- Handle errors gracefully: private videos, no captions available, age-restricted, invalid URL

### 2.2 LLM Processing → Lecture Notes
- Send the raw transcript to an LLM (e.g., Claude API) with a structured prompt asking it to:
  - Identify distinct topics/sections (based on natural breaks in content, not just timestamps)
  - Produce a title and 1–2 sentence summary for the video
  - Generate hierarchical notes: Section headings → subheadings → bullet points
  - Highlight key definitions, formulas, or important terms (bold/callout style)
  - Include timestamps next to each section so users can jump back to that part of the video
  - Optionally generate a "Key Takeaways" section at the end
- For long transcripts (>1 hour videos), chunk the transcript and process in batches, then have the LLM merge/reconcile into one coherent note set
- Output format: structured JSON (not just plain text) so the frontend can render it consistently — e.g.:
```json
{
  "title": "...",
  "summary": "...",
  "sections": [
    {
      "heading": "...",
      "timestamp": "12:34",
      "subpoints": ["...", "..."],
      "key_terms": ["..."]
    }
  ],
  "key_takeaways": ["...", "..."]
}
```

### 2.3 Flowchart Generation
- From the same structured notes, generate a flowchart/diagram showing:
  - Topic → subtopic relationships
  - Sequential flow of concepts as taught in the video (not just a static outline)
- Implementation options:
  - Have the LLM output flowchart structure in **Mermaid.js syntax** (easiest — Mermaid renders directly in-browser with a JS library, no image generation needed)
  - Render Mermaid diagrams client-side using `mermaid.js`
  - Store the raw Mermaid text in the database alongside the notes (cheap to store, easy to re-render or edit)

### 2.4 Database & Storage
- Store for each processed video:
  - Video URL, video ID, title, channel, thumbnail, duration
  - Raw transcript (optional, for reprocessing)
  - Structured notes (JSON)
  - Flowchart definition (Mermaid text)
  - Timestamps: created_at, updated_at
  - Processing status (pending / processing / done / failed)
  - Tags/category (optional, user-assigned or auto-detected by LLM, e.g. "Math", "History", "Programming")
- Suggested schema (simplified, relational):
  - `videos` table: id, url, video_id, title, channel, thumbnail_url, duration, status, created_at
  - `notes` table: id, video_id (FK), content_json, key_takeaways
  - `flowcharts` table: id, video_id (FK), mermaid_definition
  - `tags` table + `video_tags` join table (for many-to-many tagging)
  - `users` table (if multi-user support is needed, for auth and personal libraries)

### 2.5 Dashboard
- List/grid view of all processed videos: thumbnail, title, channel, date added, tags
- Search bar (by title, tag, or keyword within notes)
- Filter by tag/category
- Click into a video to see:
  - Embedded YouTube player (or link)
  - Rendered notes (collapsible sections matching timestamps)
  - Rendered flowchart (Mermaid diagram)
  - Option to jump to a specific timestamp in the video by clicking a section heading
  - Export options (PDF, Markdown)
- "Add new video" button that triggers the processing pipeline, with a progress indicator (since transcript fetch + LLM processing + flowchart generation may take 10–60 seconds)

## 3. Suggested Tech Stack

| Layer | Options |
|---|---|
| Frontend | React (Next.js) or plain React + Tailwind |
| Backend | Node.js (Express/Fastify) or Python (FastAPI) |
| Database | PostgreSQL (relational, good for structured notes + tags) or MongoDB (if you prefer storing notes as flexible JSON documents) |
| Transcript extraction | `youtube-transcript-api` (Python) / `youtube-captions-scraper` (Node) + YouTube Data API for metadata |
| LLM | Claude API (Anthropic) for note generation + flowchart Mermaid generation |
| Flowchart rendering | Mermaid.js (client-side rendering library) |
| Auth (optional) | Clerk / Auth0 / NextAuth if multi-user |
| Hosting | Vercel (frontend) + Railway/Render/Supabase (backend + DB) |
| Job queue (optional, for long videos) | BullMQ / Celery — so processing happens async and dashboard shows "processing" status |

## 4. Processing Pipeline (Step-by-Step)

1. User submits YouTube URL
2. Backend creates a `videos` row with status = "pending"
3. Backend fetches metadata (title, channel, thumbnail, duration) via YouTube Data API
4. Backend fetches transcript
5. Backend sends transcript to LLM with a prompt requesting structured JSON notes
6. Backend sends the structured notes to LLM again (or same call) requesting a Mermaid flowchart definition
7. Backend saves notes + flowchart + updates status = "done"
8. Frontend polls or uses websockets to update the dashboard in real time
9. User views the finished lecture notes + flowchart on the video's detail page

## 5. Edge Cases to Handle
- Video has no transcript/captions available (auto or manual)
- Video is very long (>2 hours) — may need chunked processing and cost/time warnings
- Video is in a non-English language — decide whether to translate or keep notes in original language
- Duplicate submissions — check if a video_id already exists before reprocessing
- Rate limits on YouTube API / LLM API — add retry logic and user-facing error messages
- Non-lecture content (music videos, vlogs) — LLM should be prompted to detect and gracefully note "This doesn't appear to be educational content" rather than forcing a lecture structure

## 6. Nice-to-Have (Future Enhancements)
- Quiz generation from the notes (auto-generated multiple-choice questions per section)
- Spaced-repetition flashcards generated from key terms
- Multi-video "course" grouping (playlists processed together into a single organized course view)
- Collaborative notes (shared dashboards for study groups)
- Voice/chat interface to "ask questions" about a specific lecture using the stored notes as context (RAG over your own notes database)
