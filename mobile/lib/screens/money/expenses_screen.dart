import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../format.dart';
import '../../i18n.dart';
import '../../state/providers.dart';
import '../../theme.dart';
import '../../widgets/error_view.dart';

class ExpensesScreen extends ConsumerWidget {
  const ExpensesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    const (String?, String?) key = (null, null);
    final async = ref.watch(expensesProvider(key));
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'expenses'))),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
            message: e.toString(), onRetry: () => ref.invalidate(expensesProvider(key))),
        data: (rows) {
          final total = rows.fold<double>(0, (s, e) => s + e.amount);
          return Column(children: [
            Container(
              width: double.infinity,
              color: AppTheme.warn.withValues(alpha: 0.10),
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(tr(context, 'total_expenses'),
                    style: TextStyle(fontSize: 11, letterSpacing: 1, color: Theme.of(context).hintColor)),
                const SizedBox(height: 4),
                Text(money(total),
                    style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: AppTheme.warn)),
              ]),
            ),
            Expanded(
              child: rows.isEmpty
                  ? Center(child: Text(tr(context, 'no_expenses')))
                  : RefreshIndicator(
                      onRefresh: () async => ref.invalidate(expensesProvider(key)),
                      child: ListView.separated(
                        itemCount: rows.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (_, i) {
                          final e = rows[i];
                          return ListTile(
                            title: Text(e.category.isEmpty ? e.kind : e.category),
                            subtitle: Text('${e.date} · ${e.accountName}'
                                '${e.note.isNotEmpty ? ' · ${e.note}' : ''}',
                                maxLines: 1, overflow: TextOverflow.ellipsis),
                            trailing: Text(money(e.amount),
                                style: const TextStyle(fontWeight: FontWeight.w700)),
                          );
                        },
                      ),
                    ),
            ),
          ]);
        },
      ),
    );
  }
}
