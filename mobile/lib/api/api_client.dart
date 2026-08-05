import 'package:dio/dio.dart';

import '../auth/secure_store.dart';
import '../config.dart';

/// One HTTP client for the whole app.
///
/// Security model:
///  * ACCESS token lives in memory only (never written to disk) and is attached
///    to every request.
///  * REFRESH token lives in the hardware keystore ([SecureStore]).
///  * On a 401 the client transparently exchanges the refresh token for a fresh
///    access token (rotating the refresh token) and retries the request once.
///  * If the refresh fails, [onSessionLost] fires so the app returns to login.
class ApiClient {
  ApiClient({this.onSessionLost}) {
    final base = BaseOptions(
      baseUrl: AppConfig.apiBaseUrl,
      connectTimeout: const Duration(seconds: 6),
      receiveTimeout: const Duration(seconds: 15),
      headers: {'Content-Type': 'application/json'},
    );
    _dio = Dio(base);
    _raw = Dio(base); // no interceptors — used for the refresh call itself
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        if (_accessToken != null) {
          options.headers['Authorization'] = 'Bearer $_accessToken';
        }
        handler.next(options);
      },
      onError: (e, handler) async {
        final is401 = e.response?.statusCode == 401;
        final retried = e.requestOptions.extra['retried'] == true;
        if (is401 && !retried) {
          final ok = await refreshSession();
          if (ok) {
            final req = e.requestOptions
              ..extra['retried'] = true
              ..headers['Authorization'] = 'Bearer $_accessToken';
            try {
              return handler.resolve(await _dio.fetch(req));
            } on DioException catch (err) {
              return handler.next(err);
            }
          }
          onSessionLost?.call();
        }
        handler.next(e);
      },
    ));
  }

  final void Function()? onSessionLost;
  final SecureStore _store = SecureStore();
  late final Dio _dio;
  late final Dio _raw;
  String? _accessToken; // memory only

  /// The server address currently in use (default or user-set).
  String get baseUrl => _dio.options.baseUrl;

  /// Apply the user's saved server address, if any, over the compiled default.
  /// Called once at startup before any request goes out.
  Future<void> loadServer() async {
    final saved = await _store.serverUrl();
    if (saved != null && saved.trim().isNotEmpty) {
      _setBase(saved.trim());
    }
  }

  /// Change the server address at run time (persisted). No rebuild needed when
  /// the network / server IP changes.
  Future<void> setServer(String url) async {
    final clean = url.trim().replaceAll(RegExp(r'/+$'), ''); // no trailing slash
    await _store.saveServerUrl(clean);
    _setBase(clean);
  }

  void _setBase(String url) {
    _dio.options.baseUrl = url;
    _raw.options.baseUrl = url;
  }

  // -- token lifecycle --------------------------------------------------
  Future<void> setSession({required String access, required String refresh}) async {
    _accessToken = access;
    await _store.saveRefreshToken(refresh);
  }

  Future<void> clearSession() async {
    _accessToken = null;
    await _store.clearRefreshToken();
  }

  bool get hasAccess => _accessToken != null;
  Future<bool> hasStoredSession() => _store.hasSession();

  Future<bool>? _refreshing;

  /// Exchange the stored refresh token for a fresh access token (rotating the
  /// refresh token). Returns false if there's no token or it's expired.
  ///
  /// Single-flight: when several requests get a 401 at once (the dashboard
  /// fires many in parallel) they all await the SAME refresh. Without this each
  /// would rotate the refresh token, invalidating the others and logging the
  /// user out for no reason.
  Future<bool> refreshSession() {
    return _refreshing ??= _doRefresh().whenComplete(() => _refreshing = null);
  }

  Future<bool> _doRefresh() async {
    final rt = await _store.refreshToken();
    if (rt == null) return false;
    try {
      final res = await _raw.post('/auth/refresh', data: {'refresh_token': rt});
      _accessToken = res.data['access_token'] as String;
      await _store.saveRefreshToken(res.data['refresh_token'] as String);
      return true;
    } on DioException {
      return false;
    }
  }

  // -- requests ---------------------------------------------------------
  Future<dynamic> get(String path, {Map<String, dynamic>? query}) async {
    try {
      final res = await _dio.get(path, queryParameters: query);
      return res.data;
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  Future<dynamic> post(String path, {Object? body}) async {
    try {
      final res = await _dio.post(path, data: body);
      return res.data;
    } on DioException catch (e) {
      throw _toApiException(e);
    }
  }

  ApiException _toApiException(DioException e) {
    if (e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.connectionError) {
      return ApiException(
          'Cannot reach the server. Check your internet or that the office '
          'server is on.',
          isNetwork: true);
    }
    final code = e.response?.statusCode ?? 0;
    if (code == 401) return ApiException('Please sign in again.', unauthorized: true);
    final detail = e.response?.data is Map ? e.response?.data['detail'] : null;
    return ApiException(detail?.toString() ?? 'Something went wrong ($code).');
  }
}

class ApiException implements Exception {
  ApiException(this.message, {this.isNetwork = false, this.unauthorized = false});
  final String message;
  final bool isNetwork;
  final bool unauthorized;
  @override
  String toString() => message;
}
