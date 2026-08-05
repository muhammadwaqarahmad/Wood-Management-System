import 'package:flutter/material.dart';

import '../i18n.dart';
import '../screens/aging_screen.dart';
import '../screens/daily_book_screen.dart';
import '../screens/master_data_screen.dart';
import '../screens/new_trade_screen.dart';
import '../screens/overdue_screen.dart';
import '../screens/payments_screen.dart';
import '../screens/search_screen.dart';
import '../screens/settings_screen.dart';
import '../screens/wood_summary_screen.dart';
import '../theme.dart';

/// Side navigation mirroring the desktop sidebar sections. The five primary
/// destinations switch the bottom tab; everything else opens as a full page.
class AppDrawer extends StatelessWidget {
  const AppDrawer({super.key, required this.currentIndex, required this.onSelectTab});
  final int currentIndex;
  final void Function(int index) onSelectTab;

  @override
  Widget build(BuildContext context) {
    return Drawer(
      child: SafeArea(
        child: ListView(
          padding: EdgeInsets.zero,
          children: [
            _brand(context),
            _header(context, tr(context, 'dashboard')),
            _tab(context, Icons.dashboard, tr(context, 'dashboard'), 0),
            _tab(context, Icons.assessment, tr(context, 'reports'), 1),
            _header(context, tr(context, 'entry')),
            _page(context, Icons.add_shopping_cart, tr(context, 'new_trade'), const NewTradeScreen()),
            _tab(context, Icons.receipt_long, tr(context, 'trades'), 4),
            _page(context, Icons.account_balance_wallet, tr(context, 'payments'),
                const PaymentsScreen()),
            _page(context, Icons.book_outlined, tr(context, 'daily_book'), const DailyBookScreen()),
            _page(context, Icons.search, tr(context, 'search'), const SearchScreen()),
            _header(context, tr(context, 'money')),
            _tab(context, Icons.account_balance_wallet_outlined, tr(context, 'money_section'), 3),
            _header(context, tr(context, 'ledgers')),
            _tab(context, Icons.menu_book, tr(context, 'ledgers_section'), 2),
            _page(context, Icons.alarm, tr(context, 'overdue'), const OverdueScreen()),
            _page(context, Icons.calendar_month, tr(context, 'aging'), const AgingScreen()),
            _page(context, Icons.forest, tr(context, 'wood_summary'), const WoodSummaryScreen()),
            _header(context, tr(context, 'manage')),
            _page(context, Icons.storage, tr(context, 'master_data'), const MasterDataScreen()),
            _page(context, Icons.settings, tr(context, 'settings'), const SettingsScreen()),
          ],
        ),
      ),
    );
  }

  Widget _brand(BuildContext context) => Container(
        width: double.infinity,
        color: AppTheme.accent,
        padding: const EdgeInsets.fromLTRB(20, 24, 20, 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.forest, color: Colors.white, size: 30),
            const SizedBox(height: 10),
            const Text('Abdul Sattar Woods',
                style: TextStyle(
                    color: Colors.white, fontSize: 18, fontWeight: FontWeight.w800)),
            const SizedBox(height: 2),
            Text(tr(context, 'view_only_companion'),
                style: const TextStyle(color: Colors.white70, fontSize: 12)),
          ],
        ),
      );

  Widget _header(BuildContext context, String text) => Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 6),
        child: Text(text.toUpperCase(),
            style: TextStyle(
                fontSize: 11,
                letterSpacing: 1.2,
                fontWeight: FontWeight.w700,
                color: Theme.of(context).hintColor)),
      );

  Widget _tab(BuildContext context, IconData icon, String label, int index) => ListTile(
        leading: Icon(icon),
        title: Text(label),
        selected: currentIndex == index,
        onTap: () {
          Navigator.pop(context);
          onSelectTab(index);
        },
      );

  Widget _page(BuildContext context, IconData icon, String label, Widget page) => ListTile(
        leading: Icon(icon),
        title: Text(label),
        onTap: () {
          Navigator.pop(context);
          Navigator.of(context).push(MaterialPageRoute(builder: (_) => page));
        },
      );
}
