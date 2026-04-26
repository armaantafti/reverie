CALENDAR_SYNC_DISABLED_MESSAGE = (
    "Google Calendar sync is disabled in beta. "
    "The app does not use local Google credential or token files."
)


def load_notes():
    return []


def save_notes(notes):
    return None


def create_event_for_note(service, note, calendar_id="primary"):
    return None


def sync_notes_to_calendar():
    print(CALENDAR_SYNC_DISABLED_MESSAGE)
    return {
        "status": "disabled",
        "detail": CALENDAR_SYNC_DISABLED_MESSAGE,
    }


if __name__ == "__main__":
    sync_notes_to_calendar()
