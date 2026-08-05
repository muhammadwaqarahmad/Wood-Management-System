import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../format.dart';
import '../i18n.dart';
import '../labels.dart';
import '../period.dart';
import '../state/providers.dart';
import '../theme.dart';
import '../widgets/bar_chart.dart';
import '../widgets/error_view.dart';
import '../widgets/kpi_tile.dart';
import '../widgets/kv_table.dart';
import '../widgets/period_filter.dart';

/// The Dashboard tab — mirrors the desktop dashboard: period filter, Period
/// summary tiles, Financial position tiles, two bar charts, and the Summary +
/// Bank-balance tables.
class DashboardTab extends ConsumerStatefulWidget {
  const DashboardTab({super.key});
  @override
  ConsumerState<DashboardTab> createState() => _DashboardTabState();
}

class _DashboardTabState extends ConsumerState<DashboardTab> {
  Period _period = Period.initial;

  @override
  Widget build(BuildContext context) {
    final range = _period.range();
    final async = ref.watch(dashboardProvider(range));
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 6),
          child: PeriodFilter(
            period: _period,
            onChanged: (p) => setState(() => _period = p),
          ),
        ),
        Expanded(
          child: RefreshIndicator(
            onRefresh: () async => ref.invalidate(dashboardProvider(range)),
            child: async.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => ErrorView(
                message: e.toString(),
                onRetry: () => ref.invalidate(dashboardProvider(range)),
              ),
              data: (d) => _Body(data: d),
            ),
          ),
        ),
      ],
    );
  }
}

class _Body extends StatelessWidget {
  const _Body({required this.data});
  final DashboardData data;

  @override
  Widget build(BuildContext context) {
    final light = Theme.of(context).brightness == Brightness.light;
    final cat = light ? AppTheme.catLight : AppTheme.catDark;
    return ListView(
      padding: const EdgeInsets.fromLTRB(12, 6, 12, 24),
      children: [
        // ---- Period summary -------------------------------------------
        _SectionLabel(tr(context, 'period_summary')),
        _TileGrid(tiles: [
          KpiTile(icon: Icons.receipt_long, label: tr(context, 'sale_bill'), value: data.card('sales'), tone: 'indigo'),
          KpiTile(icon: Icons.shopping_cart_outlined, label: tr(context, 'purchase_bill'), value: data.card('purchases'), tone: 'sky'),
          KpiTile(icon: Icons.trending_up, label: tr(context, 'profit'), value: data.card('profit'), tone: 'emerald', signed: true),
          KpiTile(icon: Icons.trending_down, label: tr(context, 'business_expenses'), value: data.card('expBusiness'), tone: 'amber'),
          KpiTile(icon: Icons.home_outlined, label: tr(context, 'house_expenses'), value: data.card('expHouse'), tone: 'amber'),
          KpiTile(icon: Icons.tag, label: tr(context, 'trades'), value: data.card('trades'), tone: 'slate', plain: true),
        ]),
        const SizedBox(height: 18),

        // ---- Financial position ---------------------------------------
        _SectionLabel(tr(context, 'financial_position')),
        _TileGrid(tiles: [
          KpiTile(icon: Icons.account_balance, label: tr(context, 'banks'), value: data.card('bankTotal'), tone: 'indigo'),
          KpiTile(icon: Icons.wallet_outlined, label: tr(context, 'cash'), value: data.card('cash'), tone: 'indigo'),
          KpiTile(icon: Icons.pie_chart_outline, label: tr(context, 'available'), value: data.card('available'), tone: 'violet', signed: true),
          KpiTile(icon: Icons.info_outline, label: tr(context, 'unclaimed'), value: data.card('unclaimed'), tone: 'amber'),
          KpiTile(icon: Icons.south_west, label: tr(context, 'to_receive'), value: data.card('receivable'), tone: 'emerald', signed: true),
          KpiTile(icon: Icons.north_east, label: tr(context, 'to_give'), value: data.card('payable'), tone: 'rose', signed: true),
          KpiTile(icon: Icons.request_quote_outlined, label: tr(context, 'loans_taken'), value: data.card('loans'), tone: 'rose', signed: true),
          KpiTile(icon: Icons.savings_outlined, label: tr(context, 'loans_given'), value: data.card('loansGiven'), tone: 'emerald', signed: true),
        ]),
        const SizedBox(height: 18),

        // ---- Charts ---------------------------------------------------
        SectionCard(
          title: tr(context, 'sales_purchases'),
          icon: Icons.bar_chart,
          child: BarChart(data: data.series, series: [
            ChartSeries(tr(context, 'sale_bill'), cat[0], (p) => p.sales),
            ChartSeries(tr(context, 'purchase_bill'), cat[1], (p) => p.purchases),
          ]),
        ),
        const SizedBox(height: 12),
        SectionCard(
          title: tr(context, 'profit_expenses'),
          icon: Icons.show_chart,
          child: BarChart(data: data.series, series: [
            ChartSeries(tr(context, 'profit'), cat[2], (p) => p.profit),
            ChartSeries(tr(context, 'expenses_word'), cat[3], (p) => p.expenses),
          ]),
        ),
        const SizedBox(height: 18),

        // ---- Summary table -------------------------------------------
        SectionCard(
          title: tr(context, 'summary'),
          icon: Icons.article_outlined,
          child: KvTable(rows: [
            for (final r in data.table)
              KvRow(
                label(r.key),
                money(r.sign < 0 ? -r.amount : r.amount),
                sign: r.sign > 0 ? '+' : r.sign < 0 ? '−' : '=',
                color: AppTheme.amount(context, r.sign == 0 ? r.amount : r.sign * r.amount),
                bold: r.sign == 0,
              ),
          ]),
        ),
        const SizedBox(height: 12),

        // ---- Bank balances (show more) -------------------------------
        _BankBalances(banks: data.banks),
      ],
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);
  final String text;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(left: 2, bottom: 8),
        child: Text(
          text.toUpperCase(),
          style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.2,
              color: Theme.of(context).hintColor),
        ),
      );
}

class _TileGrid extends StatelessWidget {
  const _TileGrid({required this.tiles});
  final List<Widget> tiles;
  @override
  Widget build(BuildContext context) {
    // 4 columns everywhere; compact tiles.
    const cols = 4;
    final ratio = MediaQuery.of(context).size.width > 640 ? 1.9 : 1.15;
    return GridView.count(
      crossAxisCount: cols,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 10,
      crossAxisSpacing: 10,
      childAspectRatio: ratio,
      children: tiles,
    );
  }
}

class _BankBalances extends StatefulWidget {
  const _BankBalances({required this.banks});
  final List<BankBalance> banks;
  @override
  State<_BankBalances> createState() => _BankBalancesState();
}

class _BankBalancesState extends State<_BankBalances> {
  static const _limit = 8;
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final banks = widget.banks;
    final shown = _expanded ? banks : banks.take(_limit).toList();
    return SectionCard(
      title: 'Bank balances',
      icon: Icons.account_balance_outlined,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          KvTable(rows: [
            for (final b in shown)
              KvRow(b.name, money(b.balance), color: AppTheme.amount(context, b.balance)),
          ]),
          if (banks.length > _limit)
            TextButton(
              onPressed: () => setState(() => _expanded = !_expanded),
              child: Text(_expanded ? 'Show less' : 'Show all (${banks.length})'),
            ),
        ],
      ),
    );
  }
}
