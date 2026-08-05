import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../format.dart';
import '../../i18n.dart';
import '../../state/providers.dart';
import '../../theme.dart';
import '../../widgets/error_view.dart';

/// One account's running statement (money in / out, running balance).
class BankBookScreen extends ConsumerWidget {
  const BankBookScreen({super.key, required this.accountId, required this.name});
  final int accountId;
  final String name;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final (int, String?, String?) key = (accountId, null, null);
    final async = ref.watch(bankBookProvider(key));
    return Scaffold(
      appBar: AppBar(title: Text(name)),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
            message: e.toString(), onRetry: () => ref.invalidate(bankBookProvider(key))),
        data: (book) => Column(
          children: [
            Container(
              width: double.infinity,
              color: AppTheme.accent.withValues(alpha: 0.08),
              padding: const EdgeInsets.all(16),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  _stat(context, tr(context, 'balance'), money(book.closing), AppTheme.amount(context, book.closing)),
                  _stat(context, tr(context, 'in'), money(book.totalIn), AppTheme.good),
                  _stat(context, tr(context, 'out'), money(book.totalOut), AppTheme.bad),
                ],
              ),
            ),
            Expanded(
              child: book.entries.isEmpty
                  ? Center(child: Text(tr(context, 'no_transactions')))
                  : ListView.separated(
                      itemCount: book.entries.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (_, i) {
                        final e = book.entries[i];
                        final isIn = e.moneyIn > 0;
                        return ListTile(
                          dense: true,
                          leading: Icon(isIn ? Icons.south_west : Icons.north_east,
                              size: 20, color: isIn ? AppTheme.good : AppTheme.bad),
                          title: Text(e.description,
                              maxLines: 1, overflow: TextOverflow.ellipsis),
                          subtitle: Text(e.date),
                          trailing: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Text((isIn ? '+ ' : '- ') + money(isIn ? e.moneyIn : e.moneyOut),
                                  style: TextStyle(
                                      fontWeight: FontWeight.w600,
                                      color: isIn ? AppTheme.good : AppTheme.bad)),
                              Text(money(e.balance),
                                  style: TextStyle(
                                      fontSize: 12, color: Theme.of(context).hintColor)),
                            ],
                          ),
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _stat(BuildContext c, String label, String value, Color color) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 10, letterSpacing: 1, color: Theme.of(c).hintColor)),
          const SizedBox(height: 2),
          Text(value, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: color)),
        ],
      );
}
