import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../format.dart';
import '../../i18n.dart';
import '../../state/providers.dart';
import '../../theme.dart';
import '../../widgets/error_view.dart';
import 'bank_book_screen.dart';

/// Bank accounts with balances; tap one to open its bank book.
class BankAccountsScreen extends ConsumerWidget {
  const BankAccountsScreen({super.key, this.title = 'Bank Accounts'});
  final String title;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(moneyAccountsProvider);
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
            message: e.toString(), onRetry: () => ref.invalidate(moneyAccountsProvider)),
        data: (accounts) {
          final total = accounts.fold<double>(0, (s, a) => s + a.closing);
          return Column(
            children: [
              Container(
                width: double.infinity,
                color: AppTheme.accent.withValues(alpha: 0.08),
                padding: const EdgeInsets.all(16),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(tr(context, 'total_available'),
                      style: TextStyle(
                          fontSize: 11, letterSpacing: 1, color: Theme.of(context).hintColor)),
                  const SizedBox(height: 4),
                  Text(money(total),
                      style: const TextStyle(
                          fontSize: 24, fontWeight: FontWeight.w800, color: AppTheme.accent)),
                ]),
              ),
              Expanded(
                child: RefreshIndicator(
                  onRefresh: () async => ref.invalidate(moneyAccountsProvider),
                  child: ListView.separated(
                    itemCount: accounts.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (_, i) {
                      final a = accounts[i];
                      return ListTile(
                        leading: Icon(a.isCash ? Icons.wallet : Icons.account_balance,
                            color: Theme.of(context).colorScheme.primary),
                        title: Text(a.name),
                        subtitle: a.accountNumber != null ? Text(a.accountNumber!) : null,
                        trailing: Text(money(a.closing),
                            style: TextStyle(
                                fontWeight: FontWeight.w700,
                                color: AppTheme.amount(context, a.closing))),
                        onTap: () => Navigator.of(context).push(MaterialPageRoute(
                            builder: (_) =>
                                BankBookScreen(accountId: a.id, name: a.name))),
                      );
                    },
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
