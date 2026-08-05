package com.example.asw_mobile

import io.flutter.embedding.android.FlutterFragmentActivity

// local_auth (biometric prompt) requires a FragmentActivity host on Android.
// The default FlutterActivity makes fingerprint/face silently fail.
class MainActivity : FlutterFragmentActivity()
