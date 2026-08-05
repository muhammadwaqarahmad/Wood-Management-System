import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/ledger_models.dart';
import '../../format.dart';
import '../../i18n.dart';
import '../../state/providers.dart';
import '../../theme.dart';
import '../../widgets/error_view.dart';

/// Financial Position — firm-wide summary, three tabs like the desktop:
/// Bank (every account), To receive, To give.
class FinancialPositionScreen extends ConsumerWidget {
  const FinancialPositionScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(positionProvider);
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: Text(tr(context, 'financial_position_page')),
          bottom: TabBar(tabs: [
            Tab(text: tr(context, 'bank')),
            Tab(text: tr(context, 'to_receive')),
            Tab(text: tr(context, 'to_give')),
          ]),
        ),
        body: async.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => ErrorView(
              message: e.toString(), onRetry: () => ref.invalidate(positionProvider)),
          data: (p) => TabBarView(children: [
            _BankTab(p: p),
            _PartyTab(
              total: p.totalReceivable,
              totalLabel: tr(context, 'total_to_receive'),
              parties: p.receivables,
            ),
            _PartyTab(
              total: p.totalPayable,
              totalLabel: tr(context, 'total_to_give'),
              parties: p.payables,
            ),
          ]),
        ),
      ),
    );
  }
}

class _TotalHeader extends StatelessWidget {
  const _TotalHeader({required this.label, required this.value});
  final String label;
  final double value;
  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: AppTheme.accent.withValues(alpha: 0.08),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label.toUpperCase(),
              style: TextStyle(
                  fontSize: 11, letterSpacing: 1, color: Theme.of(context).hintColor)),
          const SizedBox(height: 4),
          Text(signedMoney(value),
              style: TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.w800,
                  color: AppTheme.amount(context, value))),
        ],
      ),
    );
  }
}

class _BankTab extends StatelessWidget {
  const _BankTab({required this.p});
  final FinancialPosition p;
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _TotalHeader(label: tr(context, 'bank_cash_total'), value: p.grandTotal),
        Expanded(
          child: ListView.separated(
            itemCount: p.accounts.length,
            separatorBuilder: (_, __) => const Divider(height: 1),
            itemBuilder: (_, i) {
              final a = p.accounts[i];
              return ListTile(
                dense: true,
                leading: Icon(a.isCash ? Icons.wallet : Icons.account_balance,
                    size: 20, color: Theme.of(context).colorScheme.primary),
                title: Text(a.name),
                trailing: Text(money(a.closing),
                    style: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: AppTheme.amount(context, a.closing))),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _PartyTab extends StatelessWidget {
  const _PartyTab({required this.total, required this.totalLabel, required this.parties});
  final double total;
  final String totalLabel;
  final List<PositionParty> parties;
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _TotalHeader(label: totalLabel, value: total),
        Expanded(
          child: parties.isEmpty
              ? Center(
                  child: Text(tr(context, 'nothing_here'),
                      style: TextStyle(color: Theme.of(context).hintColor)))
              : ListView.separated(
                  itemCount: parties.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) {
                    final r = parties[i];
                    return ListTile(
                      dense: true,
                      title: Text(r.name),
                      subtitle: r.contact.isNotEmpty ? Text(r.contact) : null,
                      trailing: Text(signedMoney(r.amount),
                          style: TextStyle(
                              fontWeight: FontWeight.w700,
                              color: AppTheme.amount(context, r.amount))),
                    );
                  },
                ),
        ),
      ],
    );
  }
}
