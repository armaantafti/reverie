# Release 0 - Native AAB Readiness

This release prepares the Android shell for upcoming calendar, voice, and OAuth features while keeping unfinished web features hidden until later backend/web releases.

## Native capabilities included

- Android calendar insert bridge: `CalendarBridge.addEvent(...)` opens the user's calendar app with a prefilled event.
- Microphone permission: `android.permission.RECORD_AUDIO` is present for future voice capture.
- OAuth/deep-link readiness:
  - Custom scheme: `reverie://...`
  - Hosted callbacks under `https://reverie-i2b8.onrender.com/auth...`
  - Hosted callbacks under `https://reverie-i2b8.onrender.com/calendar...`
- No direct calendar read/write permission.
- No contacts, location, or background audio permissions.

## Feature rollout guardrail

This AAB only provides native readiness. Calendar buttons, voice capture, Google login, and Google Calendar sync should remain controlled by web/backend feature rollout in later releases.

## Play Console checks before upload

- Confirm Data Safety covers user content, optional audio, optional calendar events, Google profile data, and service providers.
- Confirm the privacy policy URL shows the May 16, 2026 policy update.
- Confirm microphone access is explained as user-initiated only.
- Confirm Google Calendar access is described as optional and separate from Google sign-in.

## Test checklist

- Existing username/password login still works.
- Existing notes, reminders, uploads, search, tasks, and account pages still work.
- App installs as an update over the current closed-test build.
- Opening `reverie://auth` or `reverie://calendar` routes back to the app.
- Tapping future `CalendarBridge.addEvent(...)` calls opens the Android calendar app instead of crashing.
- Mic permission is not requested on launch; it should only be requested when later web code asks for microphone access.
