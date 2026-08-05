import 'package:flutter/services.dart';
import 'package:local_auth/local_auth.dart';

/// Thin wrapper over local_auth (Touch ID / Face ID / Android BiometricPrompt).
/// The OS performs the match; the app never sees fingerprint or face data.
class Biometric {
  final _auth = LocalAuthentication();

  /// True if the device has biometric hardware AND the user has enrolled at
  /// least one fingerprint/face (or a device PIN we can fall back to).
  Future<bool> isAvailable() async {
    try {
      final supported = await _auth.isDeviceSupported();
      final canCheck = await _auth.canCheckBiometrics;
      return supported && (canCheck || await _hasAny());
    } on PlatformException {
      return false;
    }
  }

  Future<bool> _hasAny() async {
    try {
      return (await _auth.getAvailableBiometrics()).isNotEmpty;
    } on PlatformException {
      return false;
    }
  }

  /// A human label for the enrolled method(s), for button text. Reports Face,
  /// Fingerprint, or both — so face unlock (Face ID on iPhone, and Android
  /// devices with a strong face sensor) is surfaced clearly.
  Future<String> label() async {
    try {
      final types = await _auth.getAvailableBiometrics();
      final hasFace = types.contains(BiometricType.face);
      final hasPrint =
          types.contains(BiometricType.fingerprint) || types.contains(BiometricType.strong);
      if (hasFace && hasPrint) return 'Face / Fingerprint';
      if (hasFace) return 'Face';
      if (hasPrint) return 'Fingerprint';
    } on PlatformException {
      // ignore
    }
    return 'Biometric';
  }

  /// Prompt the user. Returns true only on a successful match. Falls back to
  /// the device passcode if biometrics fail (biometricOnly: false).
  Future<bool> authenticate({String reason = 'Unlock Abdul Sattar Woods'}) async {
    try {
      return await _auth.authenticate(
        localizedReason: reason,
        options: const AuthenticationOptions(
          stickyAuth: true,
          biometricOnly: false,
        ),
      );
    } on PlatformException {
      return false;
    }
  }
}
