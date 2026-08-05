import 'package:flutter/material.dart';

import '../i18n.dart';
import 'ledgers/factory_split_screen.dart';
import 'ledgers/financial_position_screen.dart';
import 'ledgers/profit_ledger_screen.dart';
import 'ledgers/trade_ledger_screen.dart';
import 'parties_screen.dart';

/// The Ledgers tab — a hub listing the six ledger pages, matching the desktop
/// Ledgers section: Financial Position, Supplier Ledger, Factory Ledger,
/// Factory Sub-ledger, Trade Ledger, Profit Ledger.
class LedgersTab extends StatelessWidget {
  const LedgersTab({super.key});

  @override
  Widget build(BuildContext context) {
    final items = <_LedgerItem>[
      _LedgerItem(Icons.pie_chart_outline, tr(context, 'financial_position_page'),
          tr(context, 'sub_financial_position'), () => const FinancialPositionScreen()),
      _LedgerItem(Icons.groups_outlined, tr(context, 'supplier_ledger'),
          tr(context, 'sub_supplier_ledger'),
          () => PartiesScreen(kind: 'supplier', title: tr(context, 'supplier_ledger'))),
      _LedgerItem(Icons.factory_outlined, tr(context, 'factory_ledger'),
          tr(context, 'sub_factory_ledger'),
          () => PartiesScreen(kind: 'factory', title: tr(context, 'factory_ledger'))),
      _LedgerItem(Icons.call_split, tr(context, 'factory_subledger'),
          tr(context, 'sub_factory_subledger'), () => const FactorySplitScreen()),
      _LedgerItem(Icons.book_outlined, tr(context, 'trade_ledger'),
          tr(context, 'sub_trade_ledger'), () => const TradeLedgerScreen()),
      _LedgerItem(Icons.trending_up, tr(context, 'profit_ledger'),
          tr(context, 'sub_profit_ledger'), () => const ProfitLedgerScreen()),
    ];
    return ListView.separated(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: items.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (_, i) {
        final it = items[i];
        return ListTile(
          leading: CircleAvatar(
            backgroundColor: Theme.of(context).colorScheme.primary.withValues(alpha: 0.12),
            child: Icon(it.icon, color: Theme.of(context).colorScheme.primary),
          ),
          title: Text(it.title, style: const TextStyle(fontWeight: FontWeight.w600)),
          subtitle: Text(it.subtitle),
          trailing: const Icon(Icons.chevron_right),
          onTap: () =>
              Navigator.of(context).push(MaterialPageRoute(builder: (_) => it.build())),
        );
      },
    );
  }
}

class _LedgerItem {
  _LedgerItem(this.icon, this.title, this.subtitle, this.build);
  final IconData icon;
  final String title;
  final String subtitle;
  final Widget Function() build;
}
