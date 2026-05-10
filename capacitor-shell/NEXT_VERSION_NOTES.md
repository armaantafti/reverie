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
