# Reverie Next Version Notes

## Android Play Console Warnings To Address

### 1. Android 15 edge-to-edge display

Play Console warning:

Apps targeting SDK 35 display edge-to-edge by default on Android 15 and later. Reverie should handle system bar insets so app content is not hidden under the status bar, navigation bar, keyboard, or gesture areas.

Implementation notes:

- Review the native Android shell for edge-to-edge behavior.
- Add explicit edge-to-edge handling using the current AndroidX approach.
- Test on Android 15 and later.
- Verify the web content inside the Capacitor WebView has enough top and bottom safe-area padding.
- Check screens with fixed bottom navigation, capture modal, account menu, item detail modal, and keyboard-open states.

### 2. Deprecated edge-to-edge APIs or parameters

Play Console warning:

The app uses deprecated APIs or parameters for edge-to-edge and window display on Android 15.

Implementation notes:

- Inspect generated Capacitor Android files and dependency versions.
- Upgrade Capacitor Android and AndroidX dependencies if needed.
- Avoid deprecated status bar/navigation bar display flags.
- Prefer the modern edge-to-edge compatibility API.
- Rebuild and check whether the Play Console warning disappears on the next uploaded bundle.

### 3. Large-screen, tablet, foldable, and orientation support

Play Console warning:

From Android 16, Android may ignore resizability and orientation restrictions for large-screen devices. Reverie should support tablets and foldables cleanly.

Implementation notes:

- Check Android manifest for orientation or resize restrictions.
- Remove unnecessary orientation locks or non-resizable settings.
- Test layout on phone, 7-inch tablet, 10-inch tablet, and foldable-like widths.
- Verify the web app responds well at wider layouts inside the Capacitor shell.
- Pay special attention to bottom navigation, capture modal, account/settings pages, Manage Entities, Search, Tasks, and item detail modals.

## Suggested Next Version Acceptance Checks

- No content hidden under Android status/navigation bars.
- Bottom app navigation remains visible and usable on gesture and 3-button navigation.
- Keyboard does not cover active input fields in capture, search, and Manage Entities.
- App works in portrait on phones and wider tablet/foldable layouts.
- Play Console warnings are reduced or cleared after uploading the next bundle.

## Next Version Enhancement Notes From Testing

### 1. Login and logout reliability

Observed issue:

Login/logout is not behaving consistently in the Android app. The current implementation mixes backend cookies with a frontend access-token fallback in localStorage.

Recommended direction:

- Move toward cookie-only authentication for the app.
- Remove or sharply limit the frontend localStorage access-token fallback after cookie persistence is confirmed.
- Ensure `/logout` clears every auth-related client state and server cookie.
- Audit all authenticated API calls to confirm they rely on cookies consistently.
- Add a startup session check that does not flash the login page while `/session` is being verified.

Refresh-token persistence fix:

- In `app.py`, make refresh-session handling return refreshed auth payloads to the route layer.
- Whenever `_refresh_session_from_cookie(request)` succeeds, update both `reverie_session` and `reverie_refresh` cookies via `_set_auth_cookies(...)`.
- Current concern: `/session` only resets cookies when `refreshed_payload` is set in the outer route, but `_get_authenticated_user()` may refresh internally and not pass the new payload back to `/session`. This can cause refreshed tokens to be lost.

Acceptance checks:

- Login once, fully close the Android app, reopen, and remain signed in.
- Logout, fully close and reopen, and remain signed out.
- Expired access-token plus valid refresh-token should refresh silently.
- Expired/invalid refresh-token should show login cleanly.

### 2. Top-bar distorted graphic

Observed issue:

On Android, a distorted graphic appears above the Reverie app header. The Reverie header should be the topmost visible app content.

Implementation notes:

- Reproduce on Android app build, not just Chrome.
- Inspect whether this is caused by splash/icon asset scaling, WebView overscroll, Android edge-to-edge inset handling, or cached top content.
- Verify that only the normal Reverie header appears at the top after launch.
- Check `viewport-fit=cover`, safe-area padding, Android `EdgeToEdge.enable(...)`, and WebView background/splash settings.

Acceptance checks:

- No stretched brain graphic appears above the real header.
- Status bar area and top safe area render cleanly on Android 15+.
- Home, Search, Tasks, Recommendations, Account, Privacy, and Manage Entities all start below the safe area.

### 3. Notification improvements

Current direction:

Use Capacitor Local Notifications for the first production notification version.

Enhancements to implement:

- Resync local notifications immediately after login.
- Resync local notifications after successful reminder/task edits.
- Resync local notifications after creating, deleting, completing, or skipping a reminder/task.
- Replace the one-way Enable Reminder Notifications action with a proper Account Settings toggle.
- Add Disable Reminder Notifications behavior that cancels all scheduled Reverie local notifications and saves the disabled setting.
- Move Account Settings from a bottom-sheet popout to a dedicated Account page so settings can grow cleanly.

Notification ID rule:

- Use the note ID as the stable source for the notification ID.
- Do not hash title or due time.
- Hash only the UUID/note ID into a deterministic numeric Android notification ID.
- If due time changes, the notification should be cancelled and rescheduled using the same note-tied ID.

Android permission check:

- Confirm `capacitor-shell/android/app/src/main/AndroidManifest.xml` contains:

```xml
<uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
```

- For Android 13 and later, request runtime notification permission before scheduling.

Acceptance checks:

- Enable notifications, grant permission, create a near-term reminder, and receive notification.
- Edit reminder due time and confirm old notification does not fire at the previous time.
- Complete/delete reminder and confirm scheduled notification is cancelled.
- Disable notifications and confirm no Reverie reminders remain scheduled.
- Re-enable notifications and confirm upcoming reminders are scheduled again.
