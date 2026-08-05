import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/ledger_models.dart';
import '../../format.dart';
import '../../i18n.dart';
import '../../period.dart';
import '../../state/providers.dart';
import '../../theme.dart';
import '../../widgets/error_view.dart';
import '../../widgets/period_filter.dart';

/// Trade Ledger — every wood line: supplier side (buy) and factory side (sell),
/// with vehicle, weight, paid-status and profit. Matches the desktop table.
class TradeLedgerScreen extends ConsumerStatefulWidget {
  const TradeLedgerScreen({super.key});
  @override
  ConsumerState<TradeLedgerScreen> createState() => _TradeLedgerScreenState();
}

class _TradeLedgerScreenState extends ConsumerState<TradeLedgerScreen> {
  Period _period = Period.initial;

  @override
  Widget build(BuildContext context) {
    final range = _period.range();
    final async = ref.watch(tradeLedgerProvider(range));
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'trade_ledger'))),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 6),
            child: PeriodFilter(
                period: _period, onChanged: (p) => setState(() => _period = p)),
          ),
          Expanded(
            child: async.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => ErrorView(
                  message: e.toString(),
                  onRetry: () => ref.invalidate(tradeLedgerProvider(range))),
              data: (t) => Column(
                children: [
                  _totalsBar(t: t),
                  Expanded(
                    child: t.rows.isEmpty
                        ? Center(
                            child: Text(tr(context, 'no_trades_period'),
                                style: TextStyle(color: Theme.of(context).hintColor)))
                        : SingleChildScrollView(
                            scrollDirection: Axis.horizontal,
                            child: SingleChildScrollView(
                              child: _table(context, t),
                            ),
                          ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _totalsChip(BuildContext c, String label, double v, {Color? color}) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 10, color: Theme.of(c).hintColor)),
          Text(money(v),
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: color)),
        ],
      );

  DataTable _table(BuildContext context, TradeLedger t) {
    Color statusColor(String s) => s == 'paid'
        ? AppTheme.good
        : s == 'partial'
            ? AppTheme.warn
            : AppTheme.bad;
    return DataTable(
      columnSpacing: 18,
      headingRowHeight: 38,
      dataRowMinHeight: 36,
      dataRowMaxHeight: 46,
      columns: [
        DataColumn(label: Text(tr(context, 'date'))),
        DataColumn(label: Text(tr(context, 'wood'))),
        DataColumn(label: Text(tr(context, 'supplier'))),
        DataColumn(label: Text(tr(context, 'buy')), numeric: true),
        DataColumn(label: Text(tr(context, 'purchase')), numeric: true),
        DataColumn(label: Text(tr(context, 'factory'))),
        DataColumn(label: Text(tr(context, 'sell')), numeric: true),
        DataColumn(label: Text(tr(context, 'sale')), numeric: true),
        DataColumn(label: Text(tr(context, 'profit')), numeric: true),
      ],
      rows: [
        for (final r in t.rows)
          DataRow(cells: [
            DataCell(Text(r.date)),
            DataCell(Text(r.wood)),
            DataCell(Row(children: [
              _dot(statusColor(r.supplierStatus)),
              const SizedBox(width: 6),
              SizedBox(width: 120, child: Text(r.supplierName, overflow: TextOverflow.ellipsis)),
            ])),
            DataCell(Text(money(r.buyRate))),
            DataCell(Text(money(r.purchaseBill))),
            DataCell(Row(children: [
              _dot(statusColor(r.factoryStatus)),
              const SizedBox(width: 6),
              SizedBox(width: 120, child: Text(r.factoryName, overflow: TextOverflow.ellipsis)),
            ])),
            DataCell(Text(money(r.sellRate))),
            DataCell(Text(money(r.saleBill))),
            DataCell(Text(money(r.profit),
                style: TextStyle(
                    color: AppTheme.amount(context, r.profit), fontWeight: FontWeight.w700))),
          ]),
      ],
    );
  }

  Widget _dot(Color c) =>
      Container(width: 8, height: 8, decoration: BoxDecoration(color: c, shape: BoxShape.circle));

  Widget _totalsBar({required TradeLedger t}) => Builder(builder: (context) {
        return Container(
          color: AppTheme.accent.withValues(alpha: 0.08),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _totalsChip(context, tr(context, 'purchase'), t.purchase),
              _totalsChip(context, tr(context, 'sale'), t.sale),
              _totalsChip(context, tr(context, 'profit'), t.profit, color: AppTheme.good),
            ],
          ),
        );
      });
}
