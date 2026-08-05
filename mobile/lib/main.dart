import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'i18n.dart';
import 'screens/home_shell.dart';
import 'screens/lock_screen.dart';
import 'screens/login_screen.dart';
import 'state/providers.dart';
import 'theme.dart';

void main() {
  runApp(const ProviderScope(child: AswApp()));
}

class AswApp extends ConsumerWidget {
  const AswApp({super.key});
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final mode = ref.watch(themeProvider);
    final locale = ref.watch(localeProvider);
    return MaterialApp(
      title: 'Abdul Sattar Woods',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: mode,
      locale: locale,
      supportedLocales: supportedLocales,
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      home: const _AuthGate(),
    );
  }
}

/// Decides which screen to show: tries a saved login first, then routes to the
/// dashboard (signed in) or the login screen.
class _AuthGate extends ConsumerStatefulWidget {
  const _AuthGate();
  @override
  ConsumerState<_AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends ConsumerState<_AuthGate> {
  late final Future<void> _restore;

  @override
  void initState() {
    super.initState();
    _restore = ref.read(authProvider.notifier).restore();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder(
      future: _restore,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Scaffold(body: Center(child: CircularProgressIndicator()));
        }
        final status = ref.watch(authProvider).status;
        return switch (status) {
          AuthStatus.loggedIn => const HomeShell(),
          AuthStatus.locked => const LockScreen(),
          AuthStatus.loggedOut || AuthStatus.unknown => const LoginScreen(),
        };
      },
    );
  }
}
