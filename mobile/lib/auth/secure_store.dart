import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Hardware-backed secure storage (iOS Keychain / Android Keystore) for the
/// refresh token and the small auth flags. The ACCESS token is never persisted
/// — it lives in memory only and is re-minted from the refresh token.
class SecureStore {
  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );

  static const _kRefresh = 'asw_refresh_token';
  static const _kBiometric = 'asw_biometric_enabled';
  static const _kLastUser = 'asw_last_username';
  static const _kServer = 'asw_server_url';
  static const _kTheme = 'asw_theme_mode';
  static const _kLang = 'asw_lang';

  Future<void> saveRefreshToken(String token) =>
      _storage.write(key: _kRefresh, value: token);
  Future<String?> refreshToken() => _storage.read(key: _kRefresh);
  Future<void> clearRefreshToken() => _storage.delete(key: _kRefresh);

  Future<bool> hasSession() async => (await refreshToken()) != null;

  Future<void> setBiometricEnabled(bool on) =>
      _storage.write(key: _kBiometric, value: on ? '1' : '0');
  Future<bool> biometricEnabled() async =>
      (await _storage.read(key: _kBiometric)) == '1';

  Future<void> saveLastUsername(String u) =>
      _storage.write(key: _kLastUser, value: u);
  Future<String?> lastUsername() => _storage.read(key: _kLastUser);

  /// User-set server address (overrides the compiled-in default). Survives
  /// logout so the phone keeps pointing at the right server.
  Future<void> saveServerUrl(String url) =>
      _storage.write(key: _kServer, value: url);
  Future<String?> serverUrl() => _storage.read(key: _kServer);

  /// Theme preference: 'light' | 'dark' | 'system'.
  Future<void> saveThemeMode(String mode) =>
      _storage.write(key: _kTheme, value: mode);
  Future<String?> themeMode() => _storage.read(key: _kTheme);

  /// Language preference: 'en' | 'ur'.
  Future<void> saveLang(String code) => _storage.write(key: _kLang, value: code);
  Future<String?> lang() => _storage.read(key: _kLang);

  /// Wipe everything on logout.
  Future<void> clearAll() async {
    await _storage.delete(key: _kRefresh);
    await _storage.delete(key: _kBiometric);
    // keep last username so the login field can pre-fill
  }
}
