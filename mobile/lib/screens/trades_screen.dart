import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../format.dart';
import '../i18n.dart';
import '../state/providers.dart';
import '../theme.dart';
import '../widgets/error_view.dart';

/// Recent trades (buy & sell), newest first, with a totals header.
class TradesTab extends ConsumerWidget {
  const TradesTab({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(tradesProvider);
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => ErrorView(
        message: e.toString(),
        onRetry: () => ref.invalidate(tradesProvider),
      ),
      data: (page) => RefreshIndicator(
        onRefresh: () async => ref.invalidate(tradesProvider),
        child: Column(
          children: [
            _TotalsHeader(count: page.totalCount, profit: page.profit),
            Expanded(
              child: page.trades.isEmpty
                  ? Center(child: Text(tr(context, 'no_trades_yet')))
                  : ListView.separated(
                      itemCount: page.trades.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (_, i) => _TradeRow(trade: page.trades[i]),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TotalsHeader extends StatelessWidget {
  const _TotalsHeader({required this.count, required this.profit});
  final int count;
  final double profit;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppTheme.accent.withValues(alpha: 0.08),
      padding: const EdgeInsets.all(16),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          _stat(context, tr(context, 'trades'), count.toString()),
          _stat(context, tr(context, 'profit'), money(profit), color: AppTheme.good),
        ],
      ),
    );
  }

  Widget _stat(BuildContext c, String label, String value, {Color? color}) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 11, letterSpacing: 1, color: Theme.of(c).hintColor)),
          const SizedBox(height: 2),
          Text(value, style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: color)),
        ],
      );
}

class _TradeRow extends StatelessWidget {
  const _TradeRow({required this.trade});
  final Trade trade;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      title: Text('${trade.bapariName}  →  ${trade.factoryName}',
          maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text('${trade.date} · ${trade.wood}'
          '${trade.vehicle.isNotEmpty ? ' · ${trade.vehicle}' : ''}'),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text(money(trade.saleBill), style: const TextStyle(fontWeight: FontWeight.w600)),
          Text('+${money(trade.profit)}',
              style: const TextStyle(fontSize: 12, color: AppTheme.good)),
        ],
      ),
    );
  }
}
