import 'package:flutter/material.dart';

import '../../i18n.dart';
import 'bank_accounts_screen.dart';
import 'cheques_screen.dart';
import 'expenses_screen.dart';
import 'loans_screen.dart';
import 'transfers_screen.dart';

/// The Money tab — a hub matching the desktop Money section:
/// Bank Accounts, Bank Book, Transfers, Expenses, Cheques, Loans.
class MoneyTab extends StatelessWidget {
  const MoneyTab({super.key});

  @override
  Widget build(BuildContext context) {
    final items = <_Item>[
      _Item(Icons.account_balance, tr(context, 'bank_accounts'), tr(context, 'sub_bank_accounts'),
          () => BankAccountsScreen(title: tr(context, 'bank_accounts'))),
      _Item(Icons.menu_book, tr(context, 'bank_book'), tr(context, 'sub_bank_book'),
          () => BankAccountsScreen(title: tr(context, 'bank_book'))),
      _Item(Icons.swap_horiz, tr(context, 'transfers'), tr(context, 'sub_transfers'),
          () => const TransfersScreen()),
      _Item(Icons.trending_down, tr(context, 'expenses'), tr(context, 'sub_expenses'),
          () => const ExpensesScreen()),
      _Item(Icons.receipt, tr(context, 'cheques'), tr(context, 'sub_cheques'),
          () => const ChequesScreen()),
      _Item(Icons.request_quote, tr(context, 'loans'), tr(context, 'sub_loans'),
          () => const LoansScreen()),
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
          onTap: () => Navigator.of(context)
              .push(MaterialPageRoute(builder: (_) => it.build())),
        );
      },
    );
  }
}

class _Item {
  _Item(this.icon, this.title, this.subtitle, this.build);
  final IconData icon;
  final String title;
  final String subtitle;
  final Widget Function() build;
}
