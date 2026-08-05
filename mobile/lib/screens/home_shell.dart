import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../i18n.dart';
import '../state/providers.dart';
import '../widgets/app_drawer.dart';
import 'dashboard_screen.dart';
import 'ledgers_hub_screen.dart';
import 'money/money_hub.dart';
import 'reports_screen.dart';
import 'search_screen.dart';
import 'settings_screen.dart';
import 'trades_screen.dart';

/// The signed-in home: bottom tabs for Dashboard, Suppliers, Factories, Trades.
/// The shell owns the app bar (title + sign-out); each tab is just its body.
class HomeShell extends ConsumerStatefulWidget {
  const HomeShell({super.key});
  @override
  ConsumerState<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends ConsumerState<HomeShell> {
  int _index = 0;
  bool _offeredBiometric = false;

  @override
  void initState() {
    super.initState();
    // One-time offer to turn on fingerprint/face unlock after the first login.
    WidgetsBinding.instance.addPostFrameCallback((_) => _maybeOfferBiometric());
  }

  Future<void> _maybeOfferBiometric() async {
    if (_offeredBiometric) return;
    final auth = ref.read(authProvider);
    if (!auth.biometricAvailable || auth.biometricEnabled) return;
    _offeredBiometric = true;
    final label = auth.biometricLabel;
    final yes = await showModalBottomSheet<bool>(
      context: context,
      builder: (ctx) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Icon(label == 'Face' ? Icons.face : Icons.fingerprint,
              size: 44, color: Theme.of(ctx).colorScheme.primary),
          const SizedBox(height: 12),
          Text('Unlock with $label?',
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800)),
          const SizedBox(height: 6),
          Text('Skip typing your password next time. You can turn this off any time.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Theme.of(ctx).hintColor)),
          const SizedBox(height: 18),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(46)),
            child: Text('Enable $label unlock'),
          ),
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Not now')),
        ]),
      ),
    );
    if (yes == true) await ref.read(authProvider.notifier).enableBiometric();
  }

  static const _titleKeys = ['dashboard', 'reports', 'ledgers', 'money', 'trades'];

  final _tabs = const [
    DashboardTab(),
    ReportsTab(),
    LedgersTab(),
    MoneyTab(),
    TradesTab(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      drawer: AppDrawer(
        currentIndex: _index,
        onSelectTab: (i) => setState(() => _index = i),
      ),
      appBar: AppBar(
        title: Text(tr(context, _titleKeys[_index])),
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            tooltip: 'Search',
            onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const SearchScreen())),
          ),
          Consumer(builder: (context, ref, _) {
            final auth = ref.watch(authProvider);
            return PopupMenuButton<String>(
              onSelected: (v) {
                final n = ref.read(authProvider.notifier);
                if (v == 'settings') {
                  Navigator.of(context).push(MaterialPageRoute(
                      builder: (_) => const SettingsScreen()));
                }
                if (v == 'logout') n.logout();
                if (v == 'bio_on') n.enableBiometric();
                if (v == 'bio_off') n.disableBiometric();
              },
              itemBuilder: (_) => [
                if (auth.biometricAvailable && !auth.biometricEnabled)
                  PopupMenuItem(
                      value: 'bio_on',
                      child: Text('${auth.biometricLabel} ${tr(context, 'unlock_suffix')}')),
                if (auth.biometricAvailable && auth.biometricEnabled)
                  PopupMenuItem(
                      value: 'bio_off',
                      child: Text('${auth.biometricLabel} ${tr(context, 'unlock_suffix')}')),
                PopupMenuItem(value: 'settings', child: Text(tr(context, 'settings'))),
                PopupMenuItem(value: 'logout', child: Text(tr(context, 'sign_out'))),
              ],
            );
          }),
        ],
      ),
      body: IndexedStack(index: _index, children: _tabs),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: [
          NavigationDestination(
              icon: const Icon(Icons.dashboard_outlined),
              selectedIcon: const Icon(Icons.dashboard),
              label: tr(context, 'nav_home')),
          NavigationDestination(
              icon: const Icon(Icons.assessment_outlined),
              selectedIcon: const Icon(Icons.assessment),
              label: tr(context, 'reports')),
          NavigationDestination(
              icon: const Icon(Icons.menu_book_outlined),
              selectedIcon: const Icon(Icons.menu_book),
              label: tr(context, 'ledgers')),
          NavigationDestination(
              icon: const Icon(Icons.account_balance_wallet_outlined),
              selectedIcon: const Icon(Icons.account_balance_wallet),
              label: tr(context, 'money')),
          NavigationDestination(
              icon: const Icon(Icons.receipt_long_outlined),
              selectedIcon: const Icon(Icons.receipt_long),
              label: tr(context, 'trades')),
        ],
      ),
    );
  }
}
