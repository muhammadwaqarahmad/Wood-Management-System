# Running the mobile app (Flutter)

One-time setup after installing the Flutter SDK.

## 1. Generate the native platform folders

The repo holds the Dart code (`lib/`) and `pubspec.yaml`. Generate the
Android/iOS wrappers **without touching `lib/`**:

```bash
cd mobile
flutter create . --platforms=android,ios --org com.abdulsattarwoods
flutter pub get
```

## 2. Point the app at the API

Edit `lib/config.dart` → `apiBaseUrl`:
- **Testing on office Wi-Fi:** `http://192.168.10.35:8000` (the server's LAN IP).
- **Production:** the Cloudflare Tunnel HTTPS URL (works from anywhere).

Run the API on the server: `python -m timber.api` (set `TIMBER_API_SECRET` in its `.env`).

## 3. Biometric config (fingerprint / face) — required

**Android** — `local_auth` needs a FragmentActivity:
1. In `android/app/src/main/kotlin/.../MainActivity.kt`, change
   `class MainActivity : FlutterActivity()` →
   `class MainActivity : FlutterFragmentActivity()`
   (import `io.flutter.embedding.android.FlutterFragmentActivity`).
2. In `android/app/src/main/AndroidManifest.xml`, inside `<manifest>`:
   ```xml
   <uses-permission android:name="android.permission.USE_BIOMETRIC"/>
   ```

**iOS** — in `ios/Runner/Info.plist`, add:
```xml
<key>NSFaceIDUsageDescription</key>
<string>Unlock Abdul Sattar Woods with Face ID</string>
```

> Building the iPhone app without a Mac: use `flutter build ipa` via a cloud
> build (Codemagic), or EAS-style CI. Android: `flutter build apk`.

## 4. Run

```bash
flutter run              # on a connected device/emulator
```

Log in once with your username + password; the app then offers **Face/
Fingerprint unlock** so you don't type the password again. See `SECURITY.md`
for how the tokens and biometric gate work.
