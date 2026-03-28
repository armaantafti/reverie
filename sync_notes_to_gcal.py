import json
import os
from datetime import datetime

WORKDIR = os.path.dirname(os.path.abspath(__file__))
NOTES_FILE = os.path.join(WORKDIR, "notes.json")


def load_notes():
    if not os.path.exists(NOTES_FILE):
        return []

    with open(NOTES_FILE, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return []

    if isinstance(data, list):
        return data
    return data.get("notes", [])


def save_notes(notes):
    tmp = NOTES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(notes, f, ensure_ascii=False, indent=2)
    os.replace(tmp, NOTES_FILE)


def parse_iso(dt_str):
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def create_event_for_note(service, note, calendar_id="primary"):
    """
    Calendar sync is temporarily disabled for deployment stability.
    Keeping this function so imports and app routes do not break.
    """
    return None


def sync_notes_to_calendar():
    """
    Temporary no-op version for deployment.
    Keeps the app stable while calendar sync is disabled.
    """
    notes = load_notes()
    if not notes:
        print("No notes to sync.")
        return

    print("Calendar sync temporarily disabled for beta deployment.")
    return


if __name__ == "__main__":
    sync_notes_to_calendar()
