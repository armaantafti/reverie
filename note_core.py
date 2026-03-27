import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from transcribe_note import (
    summarise_text,
    load_notes,
    save_notes,
    generate_id,
    NOTES_FILE,
)
from llm_extractor import extract_with_llm


def process_text_note(text: str, platform: str = "web", message_id: Optional[str] = None) -> Dict[str, Any]:
    """Process a raw text note and append it to notes.json.

    Uses LLM or algorithm based on USE_LLM toggle from transcribe_note.
    Returns the saved note dict.
    """
    transcript = (text or "").strip()

    fields = extract_with_llm(transcript)
    person_name = fields.get("person_name")
    raw_type = (fields.get("note_type") or "").lower()
    tags = fields.get("tags") or []
    entities = fields.get("entities") or []
    tag_lower = [t.lower() for t in tags]
    allowed_types = {"reminder", "recommendation", "note"}
    if raw_type not in allowed_types:
        note_type = "reminder" if "tasks" in tag_lower else "note"
    else:
        note_type = raw_type
    summary = fields.get("summary") or summarise_text(transcript, max_sentences=3)
    due_time_iso = fields.get("due_time")
    title = fields.get("title") or summary[:60]

    note = {
        "id": generate_id(),
        "created_at": datetime.now().isoformat(),
        "person_name": person_name,
        "title": title,
        "summary": summary,
        "raw_text": transcript,
        "note_type": note_type,
        "tags": tags,
        "entities": entities,
        "due_time": due_time_iso,
        "source": {
            "platform": platform,
            "message_id": message_id,
            "audio_file": None,
            "whisper_model": None,
        },
    }

    notes_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), NOTES_FILE)
    notes = load_notes(notes_path)
    notes.append(note)
    save_notes(notes_path, notes)

    return note
