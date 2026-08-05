import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/payments_models.dart';
import '../format.dart';
import '../i18n.dart';
import '../state/providers.dart';
import '../theme.dart';
import '../widgets/read_only.dart';

/// Payments page — Suppliers and Factory tabs, mirroring the desktop payment
/// screen. Read-only: the "Add Payment" button is shown but inert.
class PaymentsScreen extends StatelessWidget {
  const PaymentsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: Text(tr(context, 'payments')),
          bottom: TabBar(tabs: [
            Tab(text: tr(context, 'suppliers')),
            Tab(text: tr(context, 'factory')),
          ]),
        ),
        floatingActionButton:
            DisabledFab(icon: Icons.add, label: tr(context, 'add_payment')),
        body: const TabBarView(children: [
          _PaymentsList(kind: 'supplier'),
          _PaymentsList(kind: 'factory'),
        ]),
      ),
    );
  }
}

class _PaymentsList extends ConsumerWidget {
  const _PaymentsList({required this.kind});
  final String kind;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final key = (kind, null, null);
    final async = ref.watch(paymentsProvider(key));
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text('Could not load payments.\n$e',
              textAlign: TextAlign.center,
              style: TextStyle(color: Theme.of(context).hintColor)),
        ),
      ),
      data: (rows) {
        if (rows.isEmpty) {
          return Center(child: Text(tr(context, 'no_payments')));
        }
        final total = rows.fold<double>(0, (s, p) => s + p.amount);
        return Column(children: [
          Container(
            width: double.infinity,
            color: AppTheme.accent.withValues(alpha: 0.08),
            padding: const EdgeInsets.all(16),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                _stat(context, tr(context, 'payments'), '${rows.length}', null),
                _stat(context, tr(context, 'total'), money(total), AppTheme.accent),
              ],
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () async => ref.invalidate(paymentsProvider(key)),
              child: ListView.separated(
                itemCount: rows.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (_, i) => _tile(context, rows[i]),
              ),
            ),
          ),
        ]);
      },
    );
  }

  Widget _tile(BuildContext context, PaymentRecord p) {
    final subtitleBits = <String>[
      p.date,
      if (p.accountName.isNotEmpty && p.accountName != '—') p.accountName,
      if (p.reference.isNotEmpty) '${tr(context, 'reference')} ${p.reference}',
    ];
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: AppTheme.accent.withValues(alpha: 0.12),
        child: Icon(_methodIcon(p.method), size: 20, color: AppTheme.accent),
      ),
      title: Text(p.partyName, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(subtitleBits.join(' · '),
          maxLines: 1, overflow: TextOverflow.ellipsis),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(money(p.amount),
              style: const TextStyle(fontWeight: FontWeight.w700)),
          Text(_methodLabel(context, p.method),
              style: TextStyle(fontSize: 11, color: Theme.of(context).hintColor)),
        ],
      ),
    );
  }

  static IconData _methodIcon(String m) => switch (m) {
        'cash' => Icons.payments,
        'cheque' => Icons.receipt_long,
        'online' => Icons.smartphone,
        'bank' => Icons.account_balance,
        _ => Icons.attach_money,
      };

  static String _methodLabel(BuildContext context, String m) => switch (m) {
        'cash' => tr(context, 'method_cash'),
        'cheque' => tr(context, 'method_cheque'),
        'online' => tr(context, 'method_online'),
        'bank' => tr(context, 'method_bank'),
        _ => m,
      };

  Widget _stat(BuildContext c, String label, String value, Color? color) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: TextStyle(
                  fontSize: 10, letterSpacing: 1, color: Theme.of(c).hintColor)),
          const SizedBox(height: 2),
          Text(value,
              style: TextStyle(
                  fontSize: 18, fontWeight: FontWeight.w800, color: color)),
        ],
      );
}
