import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../format.dart';
import '../i18n.dart';
import '../labels.dart';
import '../period.dart';
import '../state/providers.dart';
import '../theme.dart';
import '../widgets/error_view.dart';
import '../widgets/kpi_tile.dart';
import '../widgets/kv_table.dart';
import '../widgets/lazy_table.dart';
import '../widgets/period_filter.dart';

/// Reports tab — Cash flow / Factories / Suppliers, with the shared period
/// filter, mirroring the desktop Reports page.
class ReportsTab extends ConsumerStatefulWidget {
  const ReportsTab({super.key});
  @override
  ConsumerState<ReportsTab> createState() => _ReportsTabState();
}

class _ReportsTabState extends ConsumerState<ReportsTab> {
  String _tab = 'cashflow';
  Period _period = Period.initial;

  static const _tabs = {
    'cashflow': 'cash_flow',
    'factory': 'factories',
    'supplier': 'suppliers',
  };

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // sub-tabs
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (final e in _tabs.entries)
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: _TabPill(
                      label: tr(context, e.value),
                      selected: _tab == e.key,
                      onTap: () => setState(() => _tab = e.key),
                    ),
                  ),
              ],
            ),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 4, 12, 6),
          child: PeriodFilter(
            period: _period,
            onChanged: (p) => setState(() => _period = p),
          ),
        ),
        Expanded(
          child: _tab == 'cashflow'
              ? _CashflowView(range: _period.range())
              : _PartyView(kind: _tab, range: _period.range()),
        ),
      ],
    );
  }
}

class _TabPill extends StatelessWidget {
  const _TabPill({required this.label, required this.selected, required this.onTap});
  final String label;
  final bool selected;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    return Material(
      color: selected ? primary.withValues(alpha: 0.12) : Colors.transparent,
      borderRadius: BorderRadius.circular(10),
      child: InkWell(
        borderRadius: BorderRadius.circular(10),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
          child: Text(label,
              style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: selected ? primary : Theme.of(context).hintColor)),
        ),
      ),
    );
  }
}

// ------------------------------------------------------------- cash flow
class _CashflowView extends ConsumerWidget {
  const _CashflowView({required this.range});
  final (String?, String?) range;

  static const _sectionTitles = {
    'position': 'Cash & bank',
    'balances': 'Receivable / payable',
    'cheques': 'Cheques in hand',
    'unclaimed': 'Unattributed money',
    'flows': "Period's flows",
  };

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(cashflowProvider(range));
    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(cashflowProvider(range)),
      child: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
            message: e.toString(), onRetry: () => ref.invalidate(cashflowProvider(range))),
        data: (r) {
          // group rows by section (skip the 'worth' headline row)
          final sections = <String, List<CashflowRow>>{};
          for (final row in r.rows) {
            if (row.section == 'worth') continue;
            sections.putIfAbsent(row.section, () => []).add(row);
          }
          return ListView(
            padding: const EdgeInsets.fromLTRB(12, 6, 12, 24),
            children: [
              _WorthHero(worth: r.worth),
              const SizedBox(height: 14),
              for (final entry in sections.entries) ...[
                SectionCard(
                  title: _sectionTitles[entry.key] ?? entry.key,
                  child: KvTable(rows: [
                    for (final row in entry.value)
                      KvRow(
                        label(row.key),
                        money(row.sign < 0 ? -row.amount : row.amount),
                        sign: row.sign > 0 ? '+' : row.sign < 0 ? '−' : '=',
                        color: AppTheme.amount(
                            context, row.sign == 0 ? row.amount : row.sign * row.amount),
                        bold: row.sign == 0,
                      ),
                  ]),
                ),
                const SizedBox(height: 12),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _WorthHero extends StatelessWidget {
  const _WorthHero({required this.worth});
  final double worth;
  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppTheme.accent, Color(0xFF0E8C63)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
      ),
      padding: const EdgeInsets.all(22),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('TOTAL BUSINESS WORTH',
              style: TextStyle(
                  color: Color(0xFFDBEAFE),
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 1.3)),
          const SizedBox(height: 6),
          Text(money(worth),
              style: TextStyle(
                  color: worth < 0 ? const Color(0xFFFECACA) : Colors.white,
                  fontSize: 30,
                  fontWeight: FontWeight.w900)),
        ],
      ),
    );
  }
}

// ---------------------------------------------------- factories / suppliers
class _PartyView extends ConsumerWidget {
  const _PartyView({required this.kind, required this.range});
  final String kind; // 'factory' | 'supplier'
  final (String?, String?) range;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isFactory = kind == 'factory';
    final args = (kind, range.$1, range.$2);
    final async = ref.watch(partyStatsProvider(args));
    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(partyStatsProvider(args)),
      child: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
            message: e.toString(), onRetry: () => ref.invalidate(partyStatsProvider(args))),
        data: (st) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Compact fixed header: overall tiles + section label.
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 6, 12, 0),
              child: _overallTiles(context, st, isFactory),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 14, 14, 6),
              child: Row(children: [
                Icon(isFactory ? Icons.factory : Icons.groups,
                    size: 18, color: AppTheme.accent),
                const SizedBox(width: 8),
                Text(isFactory ? tr(context, 'factories') : tr(context, 'suppliers'),
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
              ]),
            ),
            // Lazy, virtualized table fills the rest of the screen.
            Expanded(
              child: st.rows.isEmpty
                  ? Center(
                      child: Text(tr(context, 'no_data_period'),
                          style: TextStyle(color: Theme.of(context).hintColor)))
                  : Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      child: _partyTable(context, st, isFactory),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _overallTiles(BuildContext context, PartyStats st, bool isFactory) {
    final tiles = <Widget>[
      KpiTile(icon: Icons.tag, label: tr(context, 'trades'), value: st.o('trades'), tone: 'slate', plain: true),
      KpiTile(
          icon: isFactory ? Icons.receipt_long : Icons.shopping_cart_outlined,
          label: isFactory ? tr(context, 'total_sales') : tr(context, 'total_purchases'),
          value: st.o('volume'),
          tone: isFactory ? 'indigo' : 'sky'),
      KpiTile(icon: Icons.trending_up, label: tr(context, 'profit'), value: st.o('profit'), tone: 'emerald', signed: true),
      KpiTile(icon: Icons.south_west, label: tr(context, 'to_receive'), value: st.o('receivable'), tone: 'emerald', signed: true),
      KpiTile(icon: Icons.north_east, label: tr(context, 'to_give'), value: st.o('payable'), tone: 'rose'),
      if (isFactory)
        KpiTile(icon: Icons.alarm, label: tr(context, 'overdue_30'), value: st.o('over30'), tone: 'amber'),
      if (isFactory)
        KpiTile(icon: Icons.alarm, label: tr(context, 'overdue_60'), value: st.o('over60'), tone: 'rose'),
    ];
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

  Widget _partyTable(BuildContext context, PartyStats st, bool isFactory) {
    final volLabel = isFactory ? tr(context, 'sales') : tr(context, 'purchases');
    final columns = <TableCol>[
      TableCol(tr(context, 'name'), 150),
      TableCol(tr(context, 'trades'), 68, numeric: true),
      TableCol(volLabel, 104, numeric: true),
      TableCol(tr(context, 'profit'), 104, numeric: true),
      TableCol(tr(context, 'balance'), 104, numeric: true),
      if (isFactory) const TableCol('30d', 88, numeric: true),
      if (isFactory) const TableCol('60d', 88, numeric: true),
    ];
    Widget amt(num v, {bool colour = false}) => Text(
          money(v),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
              fontWeight: colour ? FontWeight.w600 : FontWeight.w500,
              color: colour ? AppTheme.amount(context, v) : null),
        );
    return LazyTable(
      columns: columns,
      rowCount: st.rows.length,
      rowHeight: 46,
      cellsBuilder: (i) {
        final r = st.rows[i];
        return [
          Text(r.name, maxLines: 1, overflow: TextOverflow.ellipsis),
          Text(r.trades.toString()),
          amt(r.volume),
          amt(r.profit, colour: true),
          amt(r.balance, colour: true),
          if (isFactory)
            Text(r.over30 != 0 ? money(r.over30) : '—'),
          if (isFactory)
            Text(r.over60 != 0 ? money(r.over60) : '—'),
        ];
      },
    );
  }
}
