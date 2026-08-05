import 'dart:async';
import 'package:flutter/material.dart' show ThemeMode;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/api_client.dart';
import '../api/ledger_models.dart';
import '../api/manage_models.dart';
import '../api/models.dart';
import '../api/money_models.dart';
import '../api/payments_models.dart';
import '../auth/biometric.dart';
import '../auth/secure_store.dart';

/// Keep an autoDispose provider's data cached for [d] after it first loads, so
/// navigating away and back within the window is instant instead of re-hitting
/// the network. After [d] it disposes normally (refetches next time) and frees
/// memory. A pull-to-refresh / retry still forces a fresh load via invalidate.
void _cacheFor(Ref ref, [Duration d = const Duration(minutes: 3)]) {
  final link = ref.keepAlive();
  final timer = Timer(d, link.close);
  ref.onDispose(timer.cancel);
}

// ------------------------------------------------------------- app theme
/// Light / dark / system theme, persisted so it survives restarts and applies
/// across every screen (MaterialApp reads this).
class ThemeController extends StateNotifier<ThemeMode> {
  ThemeController() : super(ThemeMode.system) {
    _load();
  }
  final _store = SecureStore();

  Future<void> _load() async {
    state = _parse(await _store.themeMode());
  }

  Future<void> setMode(ThemeMode mode) async {
    state = mode;
    await _store.saveThemeMode(mode.name);
  }

  static ThemeMode _parse(String? v) => switch (v) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.system,
      };
}

final themeProvider =
    StateNotifierProvider<ThemeController, ThemeMode>((ref) => ThemeController());

/// The single HTTP client, shared everywhere. On an unrecoverable 401 (refresh
/// failed) it asks the auth notifier to drop back to the login screen.
final Provider<ApiClient> apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(onSessionLost: () {
    ref.read(authProvider.notifier)._sessionLost();
  });
});

// --------------------------------------------------------------- auth state
enum AuthStatus { unknown, loggedOut, locked, loggedIn }

class AuthState {
  const AuthState({
    this.status = AuthStatus.unknown,
    this.user,
    this.loading = false,
    this.error,
    this.biometricAvailable = false,
    this.biometricEnabled = false,
    this.biometricLabel = 'Biometric',
    this.lastUsername,
    this.serverUrl = '',
  });

  final AuthStatus status;
  final AppUser? user;
  final bool loading;
  final String? error;
  final bool biometricAvailable;
  final bool biometricEnabled;
  final String biometricLabel;
  final String? lastUsername;
  final String serverUrl;

  bool get isLoggedIn => status == AuthStatus.loggedIn;

  AuthState copyWith({
    AuthStatus? status,
    AppUser? user,
    bool? loading,
    String? error,
    bool? biometricAvailable,
    bool? biometricEnabled,
    String? biometricLabel,
    String? lastUsername,
    String? serverUrl,
  }) =>
      AuthState(
        status: status ?? this.status,
        user: user ?? this.user,
        loading: loading ?? this.loading,
        error: error,
        biometricAvailable: biometricAvailable ?? this.biometricAvailable,
        biometricEnabled: biometricEnabled ?? this.biometricEnabled,
        biometricLabel: biometricLabel ?? this.biometricLabel,
        lastUsername: lastUsername ?? this.lastUsername,
        serverUrl: serverUrl ?? this.serverUrl,
      );
}

class AuthNotifier extends StateNotifier<AuthState> {
  AuthNotifier(this._api) : super(const AuthState());
  final ApiClient _api;
  final _store = SecureStore();
  final _bio = Biometric();

  /// App start: decide login / locked (biometric) / auto-login.
  Future<void> restore() async {
    await _api.loadServer(); // apply any user-set server address first
    final available = await _bio.isAvailable();
    final label = await _bio.label();
    final lastUser = await _store.lastUsername();
    var s = state.copyWith(
        biometricAvailable: available,
        biometricLabel: label,
        lastUsername: lastUser,
        serverUrl: _api.baseUrl);

    if (!await _api.hasStoredSession()) {
      state = s.copyWith(status: AuthStatus.loggedOut);
      return;
    }
    final biometricOn = await _store.biometricEnabled();
    s = s.copyWith(biometricEnabled: biometricOn);
    if (biometricOn && available) {
      state = s.copyWith(status: AuthStatus.locked); // wait for fingerprint/face
      return;
    }
    // No biometric gate: silently refresh the session.
    if (await _api.refreshSession() && await _loadMe()) {
      state = s.copyWith(status: AuthStatus.loggedIn);
    } else {
      await _api.clearSession();
      state = s.copyWith(status: AuthStatus.loggedOut);
    }
  }

  /// Unlock a locked session with fingerprint/face.
  Future<void> unlockWithBiometric() async {
    state = state.copyWith(loading: true, error: null);
    final ok = await _bio.authenticate(reason: 'Unlock Abdul Sattar Woods');
    if (!ok) {
      state = state.copyWith(loading: false, error: 'Unlock failed. Try again.');
      return;
    }
    if (await _api.refreshSession() && await _loadMe()) {
      state = state.copyWith(status: AuthStatus.loggedIn, loading: false);
    } else {
      await _api.clearSession();
      state = state.copyWith(status: AuthStatus.loggedOut, loading: false);
    }
  }

  Future<void> login(String username, String password) async {
    state = state.copyWith(loading: true, error: null);
    try {
      final res = await _api.post('/auth/login',
          body: {'username': username, 'password': password});
      await _api.setSession(
          access: res['access_token'] as String,
          refresh: res['refresh_token'] as String);
      await _store.saveLastUsername(username);
      state = state.copyWith(
        status: AuthStatus.loggedIn,
        user: AppUser.fromJson(res['user'] as Map<String, dynamic>),
        loading: false,
        lastUsername: username,
      );
    } on ApiException catch (e) {
      state = state.copyWith(loading: false, error: e.message);
    }
  }

  /// Turn on biometric unlock (call after a successful password login).
  Future<void> enableBiometric() async {
    if (!state.biometricAvailable) return;
    // Confirm the user can pass the biometric before we rely on it.
    if (await _bio.authenticate(reason: 'Confirm to enable unlock')) {
      await _store.setBiometricEnabled(true);
      state = state.copyWith(biometricEnabled: true);
    }
  }

  Future<void> disableBiometric() async {
    await _store.setBiometricEnabled(false);
    state = state.copyWith(biometricEnabled: false);
  }

  Future<void> logout() async {
    await _api.clearSession();
    await _store.clearAll();
    state = state.copyWith(status: AuthStatus.loggedOut, user: null, biometricEnabled: false);
  }

  void _sessionLost() {
    state = state.copyWith(status: AuthStatus.loggedOut, user: null);
  }

  /// Change the server address at run time (persisted) — used when the network
  /// or server IP changes, so no rebuild is needed.
  Future<void> setServer(String url) async {
    await _api.setServer(url);
    state = state.copyWith(serverUrl: _api.baseUrl);
  }

  Future<bool> _loadMe() async {
    try {
      final me = await _api.get('/auth/me');
      state = state.copyWith(user: AppUser.fromJson(me as Map<String, dynamic>));
      return true;
    } catch (_) {
      return false;
    }
  }
}

final StateNotifierProvider<AuthNotifier, AuthState> authProvider =
    StateNotifierProvider<AuthNotifier, AuthState>(
        (ref) => AuthNotifier(ref.read(apiClientProvider)));

// ------------------------------------------------------------- data providers
Map<String, dynamic> _rangeQuery((String?, String?) r) {
  final q = <String, dynamic>{};
  if (r.$1 != null) q['start'] = r.$1;
  if (r.$2 != null) q['end'] = r.$2;
  return q;
}

/// Dashboard summary for a date range. Family key = (startIso?, endIso?).
final dashboardProvider =
    FutureProvider.autoDispose.family<DashboardData, (String?, String?)>((ref, range) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/dashboard', query: _rangeQuery(range));
  return DashboardData.fromJson(json as Map<String, dynamic>);
});

/// Cash-flow statement for a date range.
final cashflowProvider =
    FutureProvider.autoDispose.family<CashflowReport, (String?, String?)>((ref, range) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/reports/cashflow', query: _rangeQuery(range));
  return CashflowReport.fromJson(json as Map<String, dynamic>);
});

/// Per-party performance. Family key = (kind, startIso?, endIso?).
final partyStatsProvider = FutureProvider.autoDispose
    .family<PartyStats, (String, String?, String?)>((ref, args) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final q = _rangeQuery((args.$2, args.$3))..['kind'] = args.$1;
  final json = await api.get('/reports/parties', query: q);
  return PartyStats.fromJson(json as Map<String, dynamic>);
});

/// Suppliers or factories with balances. kind = 'supplier' | 'factory'.
final partiesProvider =
    FutureProvider.autoDispose.family<List<PartyBalance>, String>((ref, kind) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/parties', query: {'kind': kind});
  return (json as List)
      .map((e) => PartyBalance.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// One party's full running statement.
final partyLedgerProvider =
    FutureProvider.autoDispose.family<LedgerStatement, int>((ref, partyId) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/parties/$partyId/ledger');
  return LedgerStatement.fromJson(json as Map<String, dynamic>);
});

/// Recent trades + totals.
final tradesProvider = FutureProvider.autoDispose<TradesPage>((ref) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/trades', query: {'limit': 100});
  return TradesPage.fromJson(json as Map<String, dynamic>);
});

// ------------------------------------------------------------- ledgers
final positionProvider = FutureProvider.autoDispose<FinancialPosition>((ref) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/ledgers/position');
  return FinancialPosition.fromJson(json as Map<String, dynamic>);
});

final tradeLedgerProvider =
    FutureProvider.autoDispose.family<TradeLedger, (String?, String?)>((ref, range) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/ledgers/trades', query: _rangeQuery(range));
  return TradeLedger.fromJson(json as Map<String, dynamic>);
});

final profitLedgerProvider = FutureProvider.autoDispose<ProfitLedger>((ref) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/ledgers/profit');
  return ProfitLedger.fromJson(json as Map<String, dynamic>);
});

final factorySplitProvider =
    FutureProvider.autoDispose.family<FactorySplit, int>((ref, factoryId) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/ledgers/factory-split/$factoryId');
  return FactorySplit.fromJson(json as Map<String, dynamic>);
});

// --------------------------------------------------------------- money
final moneyAccountsProvider = FutureProvider.autoDispose<List<BankAccount>>((ref) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/money/accounts');
  return (json as List).map((e) => BankAccount.fromJson(e as Map<String, dynamic>)).toList();
});

final bankBookProvider =
    FutureProvider.autoDispose.family<BankBook, (int, String?, String?)>((ref, args) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final q = _rangeQuery((args.$2, args.$3));
  final json = await api.get('/money/accounts/${args.$1}/book', query: q);
  return BankBook.fromJson(json as Map<String, dynamic>);
});

final transfersProvider =
    FutureProvider.autoDispose.family<List<Transfer>, (String?, String?)>((ref, range) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/money/transfers', query: _rangeQuery(range));
  return (json as List).map((e) => Transfer.fromJson(e as Map<String, dynamic>)).toList();
});

final expensesProvider =
    FutureProvider.autoDispose.family<List<Expense>, (String?, String?)>((ref, range) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/money/expenses', query: _rangeQuery(range));
  return (json as List).map((e) => Expense.fromJson(e as Map<String, dynamic>)).toList();
});

final chequesProvider =
    FutureProvider.autoDispose.family<List<Cheque>, String?>((ref, status) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final q = status == null ? null : {'status': status};
  final json = await api.get('/money/cheques', query: q);
  return (json as List).map((e) => Cheque.fromJson(e as Map<String, dynamic>)).toList();
});

final loansProvider = FutureProvider.autoDispose<List<Loan>>((ref) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/money/loans');
  return (json as List).map((e) => Loan.fromJson(e as Map<String, dynamic>)).toList();
});

// ------------------------------------------------------- payments & search
/// Saved payments for one side. Family key = (kind, startIso?, endIso?).
final paymentsProvider = FutureProvider.autoDispose
    .family<List<PaymentRecord>, (String, String?, String?)>((ref, args) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final q = _rangeQuery((args.$2, args.$3))..['kind'] = args.$1;
  final json = await api.get('/payments', query: q);
  return ((json as Map<String, dynamic>)['payments'] as List)
      .map((e) => PaymentRecord.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Global search hits for a query string. Empty query -> no request.
final searchProvider =
    FutureProvider.autoDispose.family<List<SearchHit>, String>((ref, query) async {
  final q = query.trim();
  if (q.isEmpty) return <SearchHit>[];
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/search', query: {'q': q, 'limit': 100});
  return ((json as Map<String, dynamic>)['results'] as List)
      .map((e) => SearchHit.fromJson(e as Map<String, dynamic>))
      .toList();
});

// --------------------------------------------------------- manage / reports
/// Wood types (master data).
final woodTypesProvider = FutureProvider.autoDispose<List<WoodType>>((ref) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/master/wood-types');
  return ((json as Map<String, dynamic>)['wood_types'] as List)
      .map((e) => WoodType.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Factories past their credit period.
final overdueProvider = FutureProvider.autoDispose<List<OverdueFactory>>((ref) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/reports/overdue');
  return ((json as Map<String, dynamic>)['factories'] as List)
      .map((e) => OverdueFactory.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Factory receivables split into age buckets.
final agingProvider = FutureProvider.autoDispose<List<AgingRow>>((ref) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/reports/aging');
  return ((json as Map<String, dynamic>)['rows'] as List)
      .map((e) => AgingRow.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Daily book for one day (ISO yyyy-MM-dd; null = today).
final dailyBookProvider =
    FutureProvider.autoDispose.family<List<DayEntry>, String?>((ref, day) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/reports/daily-book',
      query: day == null ? null : {'day': day});
  return ((json as Map<String, dynamic>)['entries'] as List)
      .map((e) => DayEntry.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Weight bought vs sold per wood type.
final woodSummaryProvider = FutureProvider.autoDispose<List<WoodSummary>>((ref) async {
  _cacheFor(ref);
  final api = ref.read(apiClientProvider);
  final json = await api.get('/reports/wood-summary');
  return ((json as Map<String, dynamic>)['rows'] as List)
      .map((e) => WoodSummary.fromJson(e as Map<String, dynamic>))
      .toList();
});
