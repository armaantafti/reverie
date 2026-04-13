import re
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from llm_extractor import extract_with_llm
from supabase_client import supabase_admin

PREDEFINED_TAGS = [
    "travel",
    "entertainment",
    "food",
    "study",
    "school",
    "fitness",
    "health",
    "friends",
    "family",
    "work",
    "finance",
    "personal",
    "tasks",
    "ideas",
    "goals",
    "communication",
    "documents",
    "events",
]

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
    return str(uuid.uuid4())


def _coerce_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def _clean_tags(tags: list[str]) -> list[str]:
    allowed = {tag.lower() for tag in PREDEFINED_TAGS}
    cleaned: list[str] = []
    seen: set[str] = set()

    for tag in tags:
        tag_norm = tag.strip().lower()
        if tag_norm in allowed and tag_norm not in seen:
            cleaned.append(tag_norm)
            seen.add(tag_norm)

    return cleaned


def _call_extractor(transcript: str) -> Dict[str, Any]:
    return extract_with_llm(transcript)


def _fallback_extract(transcript: str) -> Dict[str, Any]:
    summary = summarise_text(transcript, max_sentences=2)
    title_source = summary or transcript
    title = title_source.split("\n", 1)[0].strip()
    if len(title) > 60:
        title = title[:57].rstrip() + "..."

    return {
        "person_name": None,
        "note_type": "note",
        "title": title,
        "summary": summary or transcript,
        "tags": [],
        "entities": [],
        "due_time": None,
    }


def _normalise_extracted_fields(fields: Dict[str, Any], transcript: str) -> Dict[str, Any]:
    raw = fields if isinstance(fields, dict) else {}

    person_name = raw.get("person_name") if isinstance(raw.get("person_name"), str) else None
    note_type = _coerce_text(raw.get("note_type")).lower()
    summary = _coerce_text(raw.get("summary")) or summarise_text(transcript, max_sentences=2) or transcript
    title = _coerce_text(raw.get("title")) or (summary[:60] if summary else transcript[:60])
    tags = _clean_tags(_coerce_list(raw.get("tags")))[:2]
    entities = _coerce_list(raw.get("entities"))[:5]
    due_time = raw.get("due_time") if isinstance(raw.get("due_time"), str) and raw.get("due_time").strip() else None

    if note_type not in {"reminder", "recommendation", "note", "passive"}:
        note_type = "note"

    return {
        "person_name": person_name,
        "note_type": note_type,
        "title": title,
        "summary": summary,
        "tags": tags,
        "entities": entities,
        "due_time": due_time,
    }


def extract_note_fields(transcript: str) -> Dict[str, Any]:
    text = (transcript or "").strip()
    if not text:
        raise ValueError("text cannot be empty")

    try:
        fields = _call_extractor(text)
    except Exception:
        fields = _fallback_extract(text)

    return _normalise_extracted_fields(fields, text)


def build_text_note_payload(
    transcript: str,
    user_id: str,
    *,
    note_id: Optional[str] = None,
    created_at: Optional[str] = None,
) -> Dict[str, Any]:
    text = (transcript or "").strip()
    if not text:
        raise ValueError("text cannot be empty")

    resolved_user_id = (user_id or "").strip()
    if not resolved_user_id:
        raise ValueError("user_id is required")

    normalized = extract_note_fields(text)

    return {
        "id": note_id or generate_id(),
        "user_id": resolved_user_id,
        "created_at": created_at or datetime.now().isoformat(),
        "person_name": normalized["person_name"],
        "title": normalized["title"],
        "summary": normalized["summary"],
        "raw_text": text,
        "extracted_text": None,
        "image_url": None,
        "memory_type": "text",
        "note_type": normalized["note_type"],
        "tags": normalized["tags"],
        "entities": normalized["entities"],
        "due_time": normalized["due_time"],
        "calendar_event_id": None,
        "status": "pending",
        "status_note": None,
    }


def build_image_note_update(extracted_text: str, image_url: str) -> Dict[str, Any]:
    text = (extracted_text or "").strip()
    image = (image_url or "").strip() or None

    if not text:
        return {
            "person_name": None,
            "title": "Screenshot memory",
            "summary": "Image saved. OCR could not read enough text.",
            "raw_text": "",
            "extracted_text": "",
            "image_url": image,
            "memory_type": "image",
            "note_type": "passive",
            "tags": [],
            "entities": [],
            "due_time": None,
        }

    normalized = extract_note_fields(text)
    return {
        "person_name": normalized["person_name"],
        "title": normalized["title"],
        "summary": normalized["summary"],
        "raw_text": text,
        "extracted_text": text,
        "image_url": image,
        "memory_type": "image",
        "note_type": normalized["note_type"],
        "tags": normalized["tags"],
        "entities": normalized["entities"],
        "due_time": normalized["due_time"],
    }


def process_text_note(
    text: str,
    platform: str = "web",
    message_id: Optional[str] = None,
    user_id: str = "",
) -> Dict[str, Any]:
    """Process a raw text note and store it in Supabase for an authenticated user."""

    transcript = (text or "").strip()
    if not transcript:
        raise ValueError("text cannot be empty")

    resolved_user_id = (user_id or "").strip()
    if not resolved_user_id:
        raise ValueError("user_id is required")

    note = build_text_note_payload(transcript, resolved_user_id)

    try:
        supabase_admin.table("notes").insert(note).execute()
    except Exception as e:
        raise RuntimeError(f"Failed to save note to Supabase: {e}") from e

    return note
