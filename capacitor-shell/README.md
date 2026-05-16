# Reverie Capacitor Shell

This project packages the hosted Reverie web app in a Capacitor Android shell.

Hosted app URL:

```text
https://reverie-i2b8.onrender.com
```

Android package ID:

```text
com.reverie.myapp
```

Keep this package ID unchanged if this shell is meant to update the existing Google Play Console app.

The generated Android project is set to:

```text
versionCode 8
versionName 1.7
```

Increase `versionCode` again before every Play Store upload.

## Commands

```powershell
npm install
npx cap sync android
npx cap open android
```

Build the signed Play Store `.aab` from Android Studio, or configure signing and run:

```powershell
npm run build:android
```

Important: sign the Capacitor release with the same Play App Signing/upload key setup used by the current closed-testing app. Google Play will reject the update if the package ID or signing lineage does not match.

## Verification Checklist

- Login works and remains signed in after app restart.
- Add note works.
- Upload image/document works from Android file picker.
- Edit/delete note works.
- Search and smart search work.
- Tasks tab works.
- Account menu opens from every tab.
- Privacy page opens.
- Account deletion page opens.
- Android back button behavior feels correct.
- Release 0 readiness: app can open custom `reverie://...` links.
- Release 0 readiness: native calendar bridge compiles and is available to web code.

## Current Local Build Status

Capacitor Android generation and sync completed successfully.

The local debug build is currently blocked because this laptop is using Java 8:

```text
Dependency requires at least JVM runtime version 11. This build uses a Java 8 JVM.
```

A portable JDK 21 has been installed without admin rights at:

```text
D:\Documents\Reverie\tools\jdk-21-extract\jdk-21.0.11+10
```

This project points Gradle to that JDK through `android\gradle.properties`.

The Android SDK has also been installed without admin rights at:

```text
D:\Documents\Reverie\tools\android-sdk
```

Installed SDK packages:

```text
platform-tools
platforms;android-36
build-tools;36.0.0
```

Use a workspace-local Gradle cache to avoid permission issues in the Windows user `.gradle` folder:

```powershell
cd D:\Documents\Reverie\reverie-capacitor-shell\android
$env:JAVA_HOME="D:\Documents\Reverie\tools\jdk-21-extract\jdk-21.0.11+10"
$env:ANDROID_HOME="D:\Documents\Reverie\tools\android-sdk"
$env:ANDROID_SDK_ROOT=$env:ANDROID_HOME
$env:GRADLE_USER_HOME="D:\Documents\Reverie\tools\.gradle"
.\gradlew.bat assembleDebug
```

Debug APK output:

```text
D:\Documents\Reverie\reverie-capacitor-shell\android\app\build\outputs\apk\debug\app-debug.apk
```

Release app bundle output:

```text
D:\Documents\Reverie\reverie-capacitor-shell\android\app\build\outputs\bundle\release\app-release.aab
```

The generated `app-release.aab` still needs to be signed with the correct Google Play upload key/signing setup before it can replace the existing closed-testing app.
