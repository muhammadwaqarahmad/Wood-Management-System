import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../format.dart';
import '../../i18n.dart';
import '../../state/providers.dart';
import '../../theme.dart';
import '../../widgets/error_view.dart';

class LoansScreen extends ConsumerWidget {
  const LoansScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(loansProvider);
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'loans'))),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) =>
            ErrorView(message: e.toString(), onRetry: () => ref.invalidate(loansProvider)),
        data: (rows) => rows.isEmpty
            ? Center(child: Text(tr(context, 'no_loans')))
            : RefreshIndicator(
                onRefresh: () async => ref.invalidate(loansProvider),
                child: ListView.separated(
                  itemCount: rows.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) {
                    final l = rows[i];
                    return ListTile(
                      leading: Icon(l.isTaken ? Icons.call_received : Icons.call_made,
                          color: l.isTaken ? AppTheme.bad : AppTheme.good),
                      title: Text(l.lenderName),
                      subtitle: Text('${l.isTaken ? tr(context, 'taken') : tr(context, 'given')} · ${l.date}'
                          '${l.accountName.isNotEmpty ? ' · ${l.accountName}' : ''}'),
                      trailing: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(money(l.outstanding),
                              style: TextStyle(
                                  fontWeight: FontWeight.w700,
                                  color: AppTheme.amount(context, l.outstanding))),
                          Text('of ${money(l.principal)}',
                              style: TextStyle(fontSize: 11, color: Theme.of(context).hintColor)),
                        ],
                      ),
                    );
                  },
                ),
              ),
      ),
    );
  }
}
