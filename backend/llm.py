"""
Gemini LLM integration for generating structured lecture notes and Mermaid flowcharts.
"""
import os
import json
import re

from google import genai
from dotenv import load_dotenv

from transcript import chunk_transcript

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Initialize the Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.5-flash"


NOTES_PROMPT = """You are an expert educational content analyzer. Given the following YouTube video transcript, generate well-organized, structured lecture notes.

**Your output MUST be valid JSON** matching this exact schema (no markdown fences, no extra text — just the JSON object):

{{
  "title": "A clear, descriptive title for these lecture notes",
  "summary": "A 2-3 sentence summary of the video's content",
  "sections": [
    {{
      "heading": "Section heading describing the topic",
      "timestamp": "MM:SS or HH:MM:SS — the approximate timestamp where this section begins",
      "subpoints": [
        "Key point 1 — detailed and informative",
        "Key point 2 — include specific details, examples, or explanations from the video"
      ],
      "key_terms": ["Important Term 1", "Important Term 2"]
    }}
  ],
  "key_takeaways": [
    "Takeaway 1 — a high-level insight from the lecture",
    "Takeaway 2"
  ],
  "tags": ["Topic1", "Topic2", "Topic3"]
}}

**Rules:**
1. Identify natural topic sections based on content shifts, not just timestamps
2. Each section should have 3-8 detailed subpoints that capture the actual content
3. Highlight key definitions, formulas, or important terms in the key_terms array
4. Include 3-6 key takeaways at the end
5. Generate 2-5 relevant tags/categories (e.g., "Mathematics", "Programming", "History")
6. If the content does NOT appear to be educational/lecture content, still generate notes but set the first tag as "Non-Educational" and note this in the summary
7. Timestamps should reference the approximate video time where each section begins
8. Be thorough — capture the substance of the lecture, not just surface-level summaries

**TRANSCRIPT:**
{transcript}
"""


MERGE_PROMPT = """You are an expert educational content analyzer. You have been given lecture notes generated from multiple chunks of a long video transcript. Merge these into ONE coherent, well-organized set of lecture notes.

**Rules:**
1. Remove duplicate content that appeared in overlapping chunks
2. Ensure sections flow logically
3. Renumber/reorder timestamps correctly
4. Keep the same JSON schema
5. Output ONLY valid JSON (no markdown fences, no extra text)

**The JSON schema:**
{{
  "title": "...",
  "summary": "...",
  "sections": [
    {{
      "heading": "...",
      "timestamp": "...",
      "subpoints": ["..."],
      "key_terms": ["..."]
    }}
  ],
  "key_takeaways": ["..."],
  "tags": ["..."]
}}

**CHUNKED NOTES TO MERGE:**
{chunk_notes}
"""


FLOWCHART_PROMPT = """Given the following structured lecture notes, generate a Mermaid.js flowchart that visualizes the relationships between the main topics and subtopics.

**Rules:**
1. Use Mermaid `graph TD` (top-down) syntax
2. Create a clear hierarchy: Main Topic → Sections → Key concepts
3. Use meaningful, SHORT node labels (max 30 chars per label)
4. Use different node shapes to distinguish levels:
   - Main topic: `[["Topic"]]` (double brackets)
   - Sections: `["Section"]` (brackets)
   - Key concepts: `("Concept")` (rounded)
5. Show the sequential flow of concepts as taught in the video
6. Keep the diagram readable — max 15-20 nodes total
7. Output ONLY the Mermaid code, no markdown fences, no explanation
8. Make sure all node IDs are simple alphanumeric strings (no spaces or special chars)
9. Do NOT use any special characters like parentheses, brackets, or quotes inside node labels unless they are part of the Mermaid syntax for node shapes

**LECTURE NOTES:**
{notes_json}
"""


def _clean_json_response(text: str) -> str:
    """Strip markdown fences and extra whitespace from LLM JSON output."""
    text = text.strip()
    # Remove ```json ... ``` wrapping
    if text.startswith("```"):
        # Find the end of the first line (```json or ```)
        first_newline = text.index("\n")
        last_fence = text.rfind("```")
        if last_fence > first_newline:
            text = text[first_newline + 1 : last_fence]
        else:
            text = text[first_newline + 1 :]
    return text.strip()


def _clean_mermaid_response(text: str) -> str:
    """Strip markdown fences from Mermaid output."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        last_fence = text.rfind("```")
        if last_fence > first_newline:
            text = text[first_newline + 1 : last_fence]
        else:
            text = text[first_newline + 1 :]
    return text.strip()


async def generate_notes(transcript_text: str) -> dict:
    """
    Generate structured lecture notes from a transcript using Gemini.
    Handles chunked processing for long transcripts.

    Returns parsed JSON dict with notes structure.
    """
    chunks = chunk_transcript(transcript_text)

    if len(chunks) == 1:
        # Single chunk — direct processing
        prompt = NOTES_PROMPT.format(transcript=chunks[0])
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
        )
        raw = _clean_json_response(response.text)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise ValueError(f"LLM returned invalid JSON for notes: {raw[:500]}")
    else:
        # Multiple chunks — process each then merge
        chunk_results = []
        for i, chunk in enumerate(chunks):
            prompt = NOTES_PROMPT.format(transcript=chunk)
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
            )
            raw = _clean_json_response(response.text)
            try:
                chunk_notes = json.loads(raw)
            except json.JSONDecodeError:
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    chunk_notes = json.loads(match.group())
                else:
                    continue  # Skip failed chunk
            chunk_results.append(chunk_notes)

        if not chunk_results:
            raise ValueError("All transcript chunks failed to generate notes")

        if len(chunk_results) == 1:
            return chunk_results[0]

        # Merge chunks
        merge_input = json.dumps(chunk_results, indent=2)
        merge_prompt = MERGE_PROMPT.format(chunk_notes=merge_input)
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=merge_prompt,
        )
        raw = _clean_json_response(response.text)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            # Fallback: return first chunk's notes
            return chunk_results[0]


async def generate_flowchart(notes: dict) -> str:
    """
    Generate a Mermaid.js flowchart from structured notes.
    Returns Mermaid diagram definition string.
    """
    notes_json = json.dumps(notes, indent=2)
    prompt = FLOWCHART_PROMPT.format(notes_json=notes_json)

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )

    mermaid_code = _clean_mermaid_response(response.text)

    # Basic validation — should start with graph or flowchart
    if not mermaid_code.lower().startswith(("graph", "flowchart")):
        # Try to find graph/flowchart in the response
        match = re.search(r'(graph\s+\w+|flowchart\s+\w+).*', mermaid_code, re.DOTALL | re.IGNORECASE)
        if match:
            mermaid_code = match.group()
        else:
            # Fallback: generate a simple flowchart from sections
            mermaid_code = _fallback_flowchart(notes)

    return mermaid_code


def _fallback_flowchart(notes: dict) -> str:
    """Generate a simple fallback Mermaid flowchart from notes structure."""
    lines = ["graph TD"]
    title = notes.get("title", "Lecture")
    safe_title = re.sub(r'[^a-zA-Z0-9 ]', '', title)[:30]
    lines.append(f'    root[[\"{safe_title}\"]]')

    for i, section in enumerate(notes.get("sections", [])[:8]):
        heading = re.sub(r'[^a-zA-Z0-9 ]', '', section.get("heading", f"Section {i+1}"))[:25]
        node_id = f"s{i}"
        lines.append(f'    root --> {node_id}[\"{heading}\"]')

        for j, term in enumerate(section.get("key_terms", [])[:3]):
            safe_term = re.sub(r'[^a-zA-Z0-9 ]', '', term)[:20]
            term_id = f"s{i}t{j}"
            lines.append(f'    {node_id} --> {term_id}(\"{safe_term}\")')

    return "\n".join(lines)
