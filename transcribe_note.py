import argparse
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Shared defaults
NOTES_FILE = "notes.json"
IST = timezone(timedelta(hours=5, minutes=30))

# A small, safe name list fallback. Keep reading your CSV if it exists.
NAMES_CSV = Path(__file__).with_name("indian_names.csv")
COMMON_INDIAN_NAMES: set[str] = {"nakshatra"}

if NAMES_CSV.exists():
    try:
        with NAMES_CSV.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i == 0:
                    continue
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    name = parts[1].strip()
                    if name:
                        COMMON_INDIAN_NAMES.add(name.lower())
    except Exception:
        # Keep the fallback set if the CSV is malformed or unavailable.
        pass

REMINDER_KEYWORDS = {
    "remind", "reminder", "remember", "todo", "to do", "follow up", "follow-up",
    "deadline", "due", "by ", "before ", "at ", "tomorrow", "today",
}

RECOMMEND_KEYWORDS = {
    "recommend", "suggest", "movie", "song", "book", "show", "watch", "listen",
    "read", "try", "check out",
}

TAG_KEYWORDS: dict[str, list[str]] = {
    "travel": ["travel", "trip", "flight", "airport", "ticket", "hotel", "booking"],
    "entertainment": ["movie", "film", "show", "series", "watch", "music", "song", "concert"],
    "food": ["food", "eat", "dinner", "lunch", "breakfast", "restaurant", "cafe", "snack"],
    "study": ["study", "revision", "exam", "tests", "class notes", "homework"],
    "school": ["school", "class", "teacher", "assignment", "project", "club"],
    "fitness": ["fitness", "gym", "workout", "exercise", "run", "training"],
    "health": ["health", "doctor", "hospital", "medicine", "feeling better", "recovery"],
    "friends": ["friend", "friends", "buddy", "mate"],
    "family": ["family", "mom", "dad", "mother", "father", "sister", "brother", "parents"],
    "work": ["work", "office", "meeting", "project", "client", "deadline"],
    "finance": ["money", "payment", "bill", "salary", "finance", "budget", "bank"],
    "personal": ["personal", "me", "myself", "journal", "life"],
    "tasks": ["task", "todo", "to-do", "remind", "reminder", "follow up", "follow-up"],
    "ideas": ["idea", "ideas", "brainstorm", "startup", "plan", "concept"],
    "goals": ["goal", "goals", "aim", "target", "startup", "future plan"],
    "communication": ["call", "text", "message", "email", "talk", "speak", "reply"],
    "documents": ["document", "pdf", "file", "doc", "notes", "paperwork"],
    "events": ["event", "party", "festival", "function", "meetup", "gathering"],
}


def load_notes(path: str = NOTES_FILE) -> List[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []

    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("notes", [])
    return []


def save_notes(path: str, notes: List[Dict[str, Any]]) -> None:
    p = Path(path)
    tmp_path = p.with_suffix(p.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, p)


def summarise_text(text: str, max_sentences: int = 3) -> str:
    text = (text or "").strip()
    if not text:
        return ""

    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return text
    return " ".join(sentences[:max_sentences])


def classify_note_type(text: str) -> str:
    """
    Classify a note as reminder, recommendation, or note.
    Reminder wins if both sets match.
    """
    t = (text or "").lower()
    compact = t.replace(" ", "").replace("-", "")

    def any_kw(text_version: str, keywords: set[str]) -> bool:
        return any(kw in text_version for kw in keywords)

    reminder_compact = {k.replace(" ", "").replace("-", "") for k in REMINDER_KEYWORDS}
    reco_compact = {k.replace(" ", "").replace("-", "") for k in RECOMMEND_KEYWORDS}

    has_reminder = any_kw(t, REMINDER_KEYWORDS) or any_kw(compact, reminder_compact)
    has_reco = any_kw(t, RECOMMEND_KEYWORDS) or any_kw(compact, reco_compact)

    if has_reminder:
        return "reminder"
    if has_reco:
        return "recommendation"
    return "note"


def extract_person_and_tags(text: str):
    """
    Extract a likely person name and a small set of topic tags.
    """
    person_name = None
    tags: list[str] = []

    t = (text or "").strip()
    lower = t.lower()
    compact = lower.replace(" ", "").replace("-", "")

    for tag, indicators in TAG_KEYWORDS.items():
        for kw in indicators:
            kw_norm = kw.lower()
            kw_compact = kw_norm.replace(" ", "").replace("-", "")
            if kw_norm in lower or kw_compact in compact:
                tags.append(tag)
                break

    patterns = [
        r"call(?: up)? (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"text (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"message (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"email (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"remind (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"from (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"on (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"ask (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"my friend, (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
    ]

    for pat in patterns:
        m = re.search(pat, t)
        if m:
            candidate = m.group("name")
            first = candidate.split()[0].lower()
            if first in COMMON_INDIAN_NAMES:
                person_name = candidate
                break

    if person_name is None:
        for token in t.split():
            if token and token[0].isupper():
                cleaned = token.split(".")[0].strip(",:")
                if cleaned.lower() in COMMON_INDIAN_NAMES:
                    person_name = cleaned
                    break

    # De-duplicate while preserving order
    seen = set()
    deduped_tags = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            deduped_tags.append(tag)

    return person_name, deduped_tags


def extract_due_time_iso(text: str) -> Optional[str]:
    """
    Lightweight due-time parser without any extra dependencies.
    Supports ISO-like inputs only. Natural-language time parsing has been removed.
    """
    raw = (text or "").strip()
    if not raw:
        return None

    candidate = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
        dt = dt.replace(hour=10, minute=0, second=0, microsecond=0)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)

    return dt.isoformat()


def generate_id() -> str:
    return datetime.now(IST).strftime("%Y%m%dT%H%M%S%f")


def make_title(summary: str, note_type: str) -> str:
    s = (summary or "").strip()
    if not s:
        return ""

    lower = s.lower()
    for prefix in ["this is a reminder to ", "reminder to ", "reminder:", "reminder "]:
        if lower.startswith(prefix):
            s = s[len(prefix):].lstrip()
            break

    words = s.split()
    short = " ".join(words[:6])

    if note_type == "reminder":
        return f"Reminder: {short}".strip()
    if note_type == "recommendation":
        return f"Recommendation: {short}".strip()
    return short


def read_transcript_text(input_path: str) -> str:
    p = Path(input_path)
    if not p.exists():
        raise FileNotFoundError(f"Transcript file not found: {input_path}")
    return p.read_text(encoding="utf-8").strip()


def main():
    parser = argparse.ArgumentParser(
        description="Create a note from a transcript text file and append it to notes.json"
    )
    parser.add_argument("audio_path", help="Path to a .txt transcript file")
    parser.add_argument("--person-name", dest="person_name", default=None, help="Name of the person this is about (optional)")
    parser.add_argument("--title", dest="title", default=None, help="Short title for this note")
    parser.add_argument("--tags", dest="tags", default="", help="Comma-separated list of tags (optional)")
    parser.add_argument("--due", dest="due", default=None, help="Any time / deadline mentioned (free text, e.g. 'tomorrow 5pm')")
    parser.add_argument("--platform", dest="platform", default="telegram", help="Source platform (default: telegram)")
    parser.add_argument("--message-id", dest="message_id", default=None, help="Original message ID (optional)")

    args = parser.parse_args()
    input_path = args.audio_path

    if not input_path.lower().endswith(".txt"):
        raise RuntimeError(
            "Audio transcription is disabled in this build. "
            "Pass a .txt transcript file instead."
        )

    transcript = read_transcript_text(input_path)
    if not transcript:
        raise RuntimeError("Transcript file is empty.")

    from llm_extractor import extract_with_llm

    fields = extract_with_llm(transcript)

    person_name = fields.get("person_name") or args.person_name
    raw_type = str(fields.get("note_type") or "").lower()
    tags = fields.get("tags") or []
    if not isinstance(tags, list):
        tags = [str(tags)]

    entities = fields.get("entities") or []
    if not isinstance(entities, list):
        entities = [entities]

    tag_lower = [str(t).lower() for t in tags]
    allowed_types = {"reminder", "recommendation", "note"}
    if raw_type not in allowed_types:
        note_type = "reminder" if "tasks" in tag_lower else "note"
    else:
        note_type = raw_type

    summary = str(fields.get("summary") or summarise_text(transcript, max_sentences=3))
    due_time_iso = fields.get("due_time")

    raw_title = fields.get("title") or args.title
    if not raw_title:
        raw_title = summarise_text(summary or transcript, max_sentences=1)

    title = re.sub(r"^(Reminder|Recommendation)\s*:\s*", "", str(raw_title), flags=re.IGNORECASE).strip()
    title = title or make_title(summary or transcript, note_type)

    note = {
        "id": generate_id(),
        "created_at": datetime.now(IST).isoformat(),
        "person_name": person_name,
        "title": title,
        "summary": summary,
        "raw_text": transcript,
        "note_type": note_type,
        "tags": tags,
        "entities": entities,
        "due_time": due_time_iso,
        "source": {
            "platform": args.platform,
            "message_id": args.message_id,
            "text_file": os.path.basename(input_path),
        },
    }

    notes_path = Path(__file__).with_name(NOTES_FILE)
    notes = load_notes(str(notes_path))
    notes.append(note)
    save_notes(str(notes_path), notes)

    print("Saved note:")
    print(json.dumps(note, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
