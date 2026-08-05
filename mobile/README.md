# Abdul Sattar Woods — Mobile App (Flutter)

The phone app (iPhone + Android). It talks to the **API** (`timber/api/`), which
reuses the desktop's exact accounting logic — so the numbers always match.

- **Framework:** Flutter (Dart) — native, fast, one codebase for both platforms.
- **State:** Riverpod. **Networking:** Dio. **Token storage:** secure keychain.
- **Design:** the same timber-green theme as the desktop, light + dark.

Phase 1 (now): **read-only** — login, dashboard, balances, ledgers, trades.

---

## What's here

```
mobile/
  lib/
    main.dart              app entry + auth gate
    theme.dart             the green theme (matches desktop)
    config.dart            <-- set the API address here
    format.dart            money formatting
    api/
      api_client.dart      one HTTP client (adds token, clean errors)
      models.dart          data models
    state/
      providers.dart       auth + dashboard + parties providers
    screens/
      login_screen.dart
      dashboard_screen.dart
  pubspec.yaml             dependencies
  setup.ps1                one-time native-project generator
```

The native `android/` and `ios/` folders are **not** committed — they're
generated on your machine by `setup.ps1` (step 2 below).

---

## First-time setup

### 1. Install Flutter (one-time, ~15 min)
- Download: https://docs.flutter.dev/get-started/install/windows
- Unzip, add `flutter\bin` to your PATH.
- Check: `flutter doctor` (install Android Studio when it prompts, for the
  Android build tools + an emulator).

### 2. Generate the native projects
```powershell
cd mobile
.\setup.ps1
```
This creates the iPhone/Android project folders and keeps our app code.

### 3. Point the app at the API
Edit `lib/config.dart`:
```dart
static const apiBaseUrl = 'http://192.168.10.35:8000';  // server on office Wi-Fi
```
Later, after the Cloudflare Tunnel is set up, change this to the tunnel URL so
the app works from anywhere.

### 4. Start the API (on the server, or any PC that can reach the database)
```
python -m timber.api
```

### 5. Run the app
```powershell
flutter run          # on a connected phone or emulator
```

---

## Building for delivery (internal)

- **Android (easiest):**
  ```
  flutter build apk --release
  ```
  Share `build/app/outputs/flutter-apk/app-release.apk` — install directly.

- **iPhone:** needs an Apple Developer account ($99/yr). Build in the cloud
  (no Mac required) with Codemagic, or on a Mac with `flutter build ipa`, then
  distribute via TestFlight.

---

## Next phases
- **2:** record payments (both directions), still through the same core.
- **3:** full data entry + offline queue for the yard.
- **Party portal:** a read-only web statement link for factories/suppliers.
