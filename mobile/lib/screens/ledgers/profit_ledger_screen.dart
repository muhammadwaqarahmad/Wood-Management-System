import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/ledger_models.dart';
import '../../format.dart';
import '../../i18n.dart';
import '../../state/providers.dart';
import '../../theme.dart';
import '../../widgets/error_view.dart';
import '../../widgets/kpi_tile.dart';

/// Profit Ledger — every combined load with its margin, plus headline totals
/// (sales, purchases, profit, margin %). Matches the desktop.
class ProfitLedgerScreen extends ConsumerWidget {
  const ProfitLedgerScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(profitLedgerProvider);
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'profit_ledger'))),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
            message: e.toString(), onRetry: () => ref.invalidate(profitLedgerProvider)),
        data: (p) => Column(
          children: [
            _totals(context, p),
            Expanded(
              child: p.rows.isEmpty
                  ? Center(
                      child: Text(tr(context, 'no_trades_yet'),
                          style: TextStyle(color: Theme.of(context).hintColor)))
                  : SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      child: SingleChildScrollView(child: _table(context, p)),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _totals(BuildContext context, ProfitLedger p) {
    return GridView.count(
      crossAxisCount: MediaQuery.of(context).size.width > 640 ? 4 : 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      padding: const EdgeInsets.all(12),
      mainAxisSpacing: 10,
      crossAxisSpacing: 10,
      childAspectRatio: 1.75,
      children: [
        KpiTile(icon: Icons.receipt_long, label: tr(context, 'sales'), value: p.sale, tone: 'indigo'),
        KpiTile(icon: Icons.shopping_cart_outlined, label: tr(context, 'purchases'), value: p.purchase, tone: 'sky'),
        KpiTile(icon: Icons.trending_up, label: tr(context, 'profit'), value: p.profit, tone: 'emerald', signed: true),
        KpiTile(
            icon: Icons.percent,
            label: tr(context, 'margin'),
            value: p.marginPct,
            tone: 'violet',
            rawValue: '${money(p.marginPct)}%'),
      ],
    );
  }

  DataTable _table(BuildContext context, ProfitLedger p) {
    return DataTable(
      columnSpacing: 18,
      headingRowHeight: 38,
      dataRowMinHeight: 36,
      dataRowMaxHeight: 46,
      columns: [
        DataColumn(label: Text(tr(context, 'date'))),
        DataColumn(label: Text(tr(context, 'supplier'))),
        DataColumn(label: Text(tr(context, 'factory'))),
        DataColumn(label: Text(tr(context, 'buy')), numeric: true),
        DataColumn(label: Text(tr(context, 'sell')), numeric: true),
        DataColumn(label: Text(tr(context, 'profit')), numeric: true),
      ],
      rows: [
        for (final r in p.rows)
          DataRow(cells: [
            DataCell(Text(r.date)),
            DataCell(SizedBox(width: 120, child: Text(r.bapariName, overflow: TextOverflow.ellipsis))),
            DataCell(SizedBox(width: 120, child: Text(r.factoryName, overflow: TextOverflow.ellipsis))),
            DataCell(Text(money(r.bapariRate))),
            DataCell(Text(money(r.factoryRate))),
            DataCell(Text(money(r.profit),
                style: TextStyle(
                    color: AppTheme.amount(context, r.profit), fontWeight: FontWeight.w700))),
          ]),
      ],
    );
  }
}
