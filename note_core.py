import re
from datetime import datetime
from typing import Optional, Dict, Any

from llm_extractor import extract_with_llm
from supabase_client import supabase_admin

def resolve_user_id(user_id: Optional[str]) -> str:
    return (user_id or "").strip()

def summarise_text(text: str, max_sentences: int = 3) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return text
    return " ".join(sentences[:max_sentences])

def generate_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S%f")

def process_text_note(
    text: str,
    platform: str = "web",
    message_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Process a raw text note and store it in Supabase."""

    transcript = (text or "").strip()
    if not transcript:
        raise ValueError("text cannot be empty")

    resolved_user_id = resolve_user_id(user_id)
    if not resolved_user_id:
        raise ValueError("user_id is required")

    fields = extract_with_llm(transcript)

    person_name = fields.get("person_name")
    raw_type = (fields.get("note_type") or "").lower()
    tags = fields.get("tags") or []
    entities = fields.get("entities") or []

    if isinstance(tags, str):
        tags = [tags]
    elif not isinstance(tags, list):
        tags = list(tags) if tags else []

    if isinstance(entities, str):
        entities = [entities]
    elif not isinstance(entities, list):
        entities = list(entities) if entities else []

    tag_lower = [str(t).lower() for t in tags]
    allowed_types = {"reminder", "recommendation", "note"}

    if raw_type not in allowed_types:
        note_type = "reminder" if "tasks" in tag_lower else "note"
    else:
        note_type = raw_type

    summary = fields.get("summary") or summarise_text(transcript, max_sentences=3)
    due_time_iso = fields.get("due_time")
    title = fields.get("title") or (summary[:60] if summary else transcript[:60])

    note = {
        "id": generate_id(),
        "user_id": resolved_user_id,
        "created_at": datetime.now().isoformat(),
        "person_name": person_name,
        "title": title,
        "summary": summary,
        "raw_text": transcript,
        "note_type": note_type,
        "tags": tags,
        "entities": entities,
        "due_time": due_time_iso,
        "calendar_event_id": None,
        "source": {
            "platform": platform,
            "message_id": message_id,
        },
    }

    try:
        supabase_admin.table("notes").insert(note).execute()
    except Exception as e:
        raise RuntimeError(f"Failed to save note to Supabase: {e}") from e

    return note
