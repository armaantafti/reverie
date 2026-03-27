import argparse
import json
import os
import re
from datetime import datetime, timedelta

# Ensure ffmpeg is on PATH for Whisper
FFMPEG_DIR = r"C:\ffmpeg-master-latest-win64-gpl-shared\bin"  # used only when you run on audio
if os.path.isdir(FFMPEG_DIR) and FFMPEG_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = FFMPEG_DIR + os.pathsep + os.environ.get("PATH", "")

import whisper
try:
    import dateparser
except ImportError:
    dateparser = None


# Load common Indian first names from CSV
NAMES_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "indian_names.csv")
COMMON_INDIAN_NAMES: set[str] = {"nakshatra"}
if os.path.exists(NAMES_CSV):
    try:
        with open(NAMES_CSV, "r", encoding="utf-8") as f:
            # Skip header, read Name column
            for i, line in enumerate(f):
                if i == 0:
                    continue
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    name = parts[1].strip()
                    if name:
                        COMMON_INDIAN_NAMES.add(name.lower())
    except Exception:
        COMMON_INDIAN_NAMES = set()


NOTES_FILE = "notes.json"


def load_notes(path: str):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return []
    if isinstance(data, list):
        return data
    return data.get("notes", [])


def save_notes(path: str, notes):
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def summarise_text(text: str, max_sentences: int = 3) -> str:
    text = text.strip()
    if not text:
        return ""
    # simple sentence split on punctuation
    sentences = re.split(r"(?<=[.!?]) +", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    return " ".join(sentences[:max_sentences])


def classify_note_type(text: str) -> str:
    """Classify note as reminder vs recommendation vs note.

    - Reminder wins if both sets match.
    - Recommendation only if recommendation words appear and no strong reminder words.
    """
    t = text.lower()
    compact = t.replace(" ", "").replace("-", "")

    def any_kw(text_version: str, keywords: set[str]) -> bool:
        return any(kw in text_version for kw in keywords)

    has_reminder = any_kw(t, REMINDER_KEYWORDS) or any_kw(compact, {k.replace(" ", "").replace("-", "") for k in REMINDER_KEYWORDS})
    has_reco = any_kw(t, RECOMMEND_KEYWORDS) or any_kw(compact, {k.replace(" ", "").replace("-", "") for k in RECOMMEND_KEYWORDS})

    if has_reminder:
        return "reminder"
    if has_reco:
        return "recommendation"
    return "note"


def extract_person_and_tags(text: str):
    """Extract main person name and simple domain tags (flight, movie, book, etc.)."""
    person_name = None
    tags: list[str] = []

    t = text.strip()
    lower = t.lower()
    compact = lower.replace(" ", "").replace("-", "")

    # Domain tags via TAG_KEYWORDS (supports simple space/hyphen normalisation)
    for tag, indicators in TAG_KEYWORDS.items():
        for kw in indicators:
            kw_norm = kw.lower()
            kw_compact = kw_norm.replace(" ", "").replace("-", "")
            if kw_norm in lower or kw_compact in compact:
                # Special case: avoid tagging flight when "check in" is about a person/health
                if tag == "flight":
                    has_flight_words = any(w in lower for w in ["flight", "airport", "boarding pass", "gate", "terminal", "ticket"])
                    has_health_words = any(w in lower for w in ["health", "feels", "feeling", "better", "recovery"])
                    has_person = person_name is not None
                    if not has_flight_words and (has_person or has_health_words):
                        break  # skip flight tag in this context
                tags.append(tag)
                break

    # Try to extract a person after verbs like call/text/message/email/remind/from/on/ask/my friend
    patterns = [
        r"call(?: up)? (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"text (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"message (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"email (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"remind (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"from (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",
        r"on (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",             # "check in on Aarush"
        r"ask (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",            # "Ask Arjun to send ..."
        r"my friend, (?P<name>[A-Z][a-z]+(?: [A-Z][a-z]+)*)",     # "from my friend, Pat Dargan"
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            candidate = m.group("name")
            first = candidate.split()[0].lower()
            if first in COMMON_INDIAN_NAMES:
                person_name = candidate
                break

    # Fallback: scan capitalised tokens against names dataset
    if person_name is None:
        for token in t.split():
            if token and token[0].isupper():
                first = token.split(".")[0].strip(",:")  # basic cleanup
                if first.lower() in COMMON_INDIAN_NAMES:
                    person_name = first
                    break

    return person_name, tags


def extract_due_time_iso(text: str) -> str | None:
    """Parse natural-language time to an ISO datetime string (future-oriented)."""
    if not dateparser:
        return None

    from dateparser.search import search_dates

    # Try to find explicit date/time phrases first
    results = search_dates(
        text,
        settings={
            "PREFER_DATES_FROM": "future",
        },
    )
    if results:
        # results is list of (matched_text, datetime)
        _, dt = results[0]
    else:
        dt = dateparser.parse(text, settings={"PREFER_DATES_FROM": "future"})

    if not dt:
        return None

    if not isinstance(dt, datetime):
        dt = datetime(dt.year, dt.month, dt.day)

    # If parsed datetime has no time info, default to 10:00
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
        dt = dt.replace(hour=10, minute=0, second=0, microsecond=0)

    # If no tzinfo, assume Asia/Kolkata (+05:30) for you
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=None)
    return dt.isoformat()


def generate_id() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def make_title(summary: str, note_type: str) -> str:
    """Generate a short title from the summary + note type (e.g. "Reminder: borrow book")."""
    s = (summary or "").strip()
    if not s:
        return ""

    # Normalise leading boilerplate
    lower = s.lower()
    for prefix in ["this is a reminder to ", "reminder to ", "reminder:", "reminder "]:
        if lower.startswith(prefix):
            s = s[len(prefix):].lstrip()
            break

    # Take the first ~6 words as the core action
    words = s.split()
    short = " ".join(words[:6])

    # Add type prefix for clarity
    if note_type == "reminder":
        return f"Reminder: {short}".strip()
    if note_type == "recommendation":
        return f"Recommendation: {short}".strip()
    return short


def main():
    parser = argparse.ArgumentParser(description="Transcribe a voice note with Whisper and append to notes.json")
    parser.add_argument("audio_path", help="Path to the audio file")
    parser.add_argument("--person-name", dest="person_name", default=None, help="Name of the person this is about (optional)")
    parser.add_argument("--title", dest="title", default=None, help="Short title for this note")
    parser.add_argument("--tags", dest="tags", default="", help="Comma-separated list of tags (optional)")
    parser.add_argument("--due", dest="due", default=None, help="Any time / deadline mentioned (free text, e.g. 'tomorrow 5pm')")
    parser.add_argument("--platform", dest="platform", default="telegram", help="Source platform (default: telegram)")
    parser.add_argument("--message-id", dest="message_id", default=None, help="Original message ID (optional)")
    parser.add_argument("--model", dest="model_name", default="small", help="Whisper model name (tiny, base, small, medium, large)")

    args = parser.parse_args()

    audio_path = args.audio_path

    # If given a .txt file, treat it as already-transcribed text and skip Whisper
    if audio_path.lower().endswith(".txt"):
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Transcript file not found: {audio_path}")
        with open(audio_path, "r", encoding="utf-8") as f:
            transcript = f.read().strip()
    else:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        print(f"Loading Whisper model '{args.model_name}'...")
        model = whisper.load_model(args.model_name)

        print(f"Transcribing {audio_path}...")
        result = model.transcribe(audio_path, fp16=False)
        transcript = (result.get("text") or "").strip()

    from llm_extractor import extract_with_llm
    fields = extract_with_llm(transcript)

    person_name = fields.get("person_name")
    raw_type = (fields.get("note_type") or "").lower()
    tags = fields.get("tags") or []
    tag_lower = [t.lower() for t in tags]
    allowed_types = {"reminder", "recommendation", "note"}
    if raw_type not in allowed_types:
        note_type = "reminder" if "tasks" in tag_lower else "note"
    else:
        note_type = raw_type
    summary = fields.get("summary") or summarise_text(transcript, max_sentences=3)
    due_time_iso = fields.get("due_time")
    # In LLM mode, trust the model's title, but strip leading "Reminder:" / "Recommendation:" if present.
    # If the model omits title, derive one from the first sentence of the summary instead of truncating mid-phrase.
    raw_title = fields.get("title")
    if not raw_title:
        first_sent = summarise_text(summary or transcript, max_sentences=1)
        raw_title = first_sent
    title = re.sub(r"^(Reminder|Recommendation)\s*:\s*", "", raw_title or "", flags=re.IGNORECASE).strip()

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
            "platform": args.platform,
            "message_id": args.message_id,
            "audio_file": os.path.basename(audio_path),
            "whisper_model": args.model_name,
        },
    }

    notes_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), NOTES_FILE)
    notes = load_notes(notes_path)
    notes.append(note)
    save_notes(notes_path, notes)

    print("Saved note:")
    print(json.dumps(note, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
