/// Where the app finds the API.
///
/// - While testing on the office Wi-Fi, point at the server's LAN address.
/// - In production, point at the Cloudflare Tunnel URL (works from anywhere).
///
/// Change this one line per environment. Later this can move to a build flag.
class AppConfig {
  /// The API base URL. No trailing slash.
  ///
  /// Default = the office LAN server (192.168.10.35, API on port 8000).
  /// Override at run time WITHOUT editing code, e.g. to point at a local API:
  ///   flutter run -d windows --dart-define=API_URL=http://127.0.0.1:8000
  static const apiBaseUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://192.168.10.35:8000',
  );

  // Production (after the Cloudflare Tunnel is set up), e.g.:
  // static const apiBaseUrl = 'https://api.abdulsattarwoods.com';
}
