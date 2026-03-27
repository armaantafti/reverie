import json
import os
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

WORKDIR = os.path.dirname(os.path.abspath(__file__))
NOTES_FILE = os.path.join(WORKDIR, "notes.json")
CREDENTIALS_FILE = os.path.join(WORKDIR, "google_calendar_credentials.json")
TOKEN_FILE = os.path.join(WORKDIR, "google_calendar_token.json")


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


def get_calendar_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    service = build("calendar", "v3", credentials=creds)
    return service


def parse_iso(dt_str):
    try:
        return datetime.fromisoformat(dt_str)
    except Exception:
        return None


def create_event_for_note(service, note, calendar_id="primary"):
    due_iso = note.get("due_time")
    if not due_iso:
        return None
    due_dt = parse_iso(due_iso)
    if not due_dt:
        return None

    # Event: 30 minutes before due_time, lasting 30 minutes
    start_dt = due_dt - timedelta(minutes=30)
    end_dt = due_dt

    summary = note.get("title") or note.get("summary") or "Reminder"
    description_lines = []
    if note.get("summary"):
        description_lines.append(note["summary"])
    if note.get("person_name"):
        description_lines.append(f"Person: {note['person_name']}")
    if note.get("note_type"):
        description_lines.append(f"Type: {note['note_type']}")
    tags = note.get("tags") or []
    if tags:
        description_lines.append("Tags: " + ", ".join(tags))

    description = "\n".join(description_lines) if description_lines else None

    event_body = {
        "summary": summary,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
    }
    if description:
        event_body["description"] = description

    created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    return created


def sync_notes_to_calendar():
    notes = load_notes()
    if not notes:
        print("No notes to sync.")
        return

    service = get_calendar_service()

    updated = False
    for note in notes:
        # Only reminders with due_time, and not yet synced
        if note.get("note_type") != "reminder":
            continue
        if not note.get("due_time"):
            continue
        if note.get("calendar_event_id"):
            continue

        print(f"Creating event for note {note.get('id')}...")
        event = create_event_for_note(service, note)
        if event and event.get("id"):
            note["calendar_event_id"] = event["id"]
            updated = True
            print(f"Created event: {event['id']}")

    if updated:
        save_notes(notes)
        print("Notes updated with calendar_event_id.")
    else:
        print("No new events created.")


if __name__ == "__main__":
    sync_notes_to_calendar()
