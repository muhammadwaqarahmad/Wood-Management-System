import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../api/ledger_models.dart';
import '../../format.dart';
import '../../i18n.dart';
import '../../state/providers.dart';
import '../../theme.dart';
import '../../widgets/error_view.dart';

/// Factory Sub-ledger — pick a factory, then see its two-sided (weekly /
/// irregular) split statement. Mirrors the desktop sub-ledger.
class FactorySplitScreen extends ConsumerWidget {
  const FactorySplitScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(partiesProvider('factory'));
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'factory_subledger'))),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
            message: e.toString(), onRetry: () => ref.invalidate(partiesProvider('factory'))),
        data: (list) => ListView.separated(
          itemCount: list.length,
          separatorBuilder: (_, __) => const Divider(height: 1),
          itemBuilder: (_, i) {
            final f = list[i];
            return ListTile(
              leading: const Icon(Icons.factory_outlined),
              title: Text(f.name),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) => _SplitDetail(factoryId: f.id, name: f.name),
              )),
            );
          },
        ),
      ),
    );
  }
}

class _SplitDetail extends ConsumerWidget {
  const _SplitDetail({required this.factoryId, required this.name});
  final int factoryId;
  final String name;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(factorySplitProvider(factoryId));
    return Scaffold(
      appBar: AppBar(title: Text(name)),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
            message: e.toString(),
            onRetry: () => ref.invalidate(factorySplitProvider(factoryId))),
        data: (st) => Column(
          children: [
            _header(context, st),
            Expanded(
              child: st.entries.isEmpty
                  ? Center(
                      child: Text(tr(context, 'no_entries'),
                          style: TextStyle(color: Theme.of(context).hintColor)))
                  : ListView.separated(
                      itemCount: st.entries.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (_, i) => _EntryRow(e: st.entries[i]),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _header(BuildContext context, FactorySplit st) {
    return Container(
      width: double.infinity,
      color: AppTheme.accent.withValues(alpha: 0.08),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${tr(context, 'split_rate')}  ${money(st.splitRate)}',
              style: TextStyle(fontSize: 11, letterSpacing: 1, color: Theme.of(context).hintColor)),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              _chip(context, tr(context, 'weekly'), st.closingLeft),
              _chip(context, tr(context, 'irregular'), st.closingRight),
              _chip(context, tr(context, 'total'), st.closingTotal, bold: true),
            ],
          ),
        ],
      ),
    );
  }

  Widget _chip(BuildContext c, String label, double v, {bool bold = false}) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: TextStyle(fontSize: 10, color: Theme.of(c).hintColor)),
          Text(signedMoney(v),
              style: TextStyle(
                  fontSize: bold ? 18 : 15,
                  fontWeight: FontWeight.w800,
                  color: AppTheme.amount(c, v))),
        ],
      );
}

class _EntryRow extends StatelessWidget {
  const _EntryRow({required this.e});
  final SplitEntry e;
  @override
  Widget build(BuildContext context) {
    final isPay = e.isPayment;
    final title = isPay
        ? (e.detail.isNotEmpty ? e.detail : tr(context, 'payment'))
        : [e.wood, e.vehicle].where((s) => s.isNotEmpty).join(' · ');
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(isPay ? Icons.south_west : Icons.local_shipping_outlined,
                size: 16, color: isPay ? AppTheme.good : AppTheme.accent),
            const SizedBox(width: 6),
            Expanded(
                child: Text(title.isEmpty ? tr(context, isPay ? 'payment' : 'load') : title,
                    maxLines: 1, overflow: TextOverflow.ellipsis)),
            Text(e.date, style: TextStyle(fontSize: 11, color: Theme.of(context).hintColor)),
          ]),
          const SizedBox(height: 4),
          Row(children: [
            Expanded(child: _side(context, tr(context, 'weekly'),
                isPay ? -e.leftPayment : e.leftNet, e.leftBalance)),
            Expanded(child: _side(context, tr(context, 'irregular'),
                isPay ? -e.rightPayment : e.rightAmount, e.rightBalance)),
          ]),
        ],
      ),
    );
  }

  Widget _side(BuildContext c, String label, double amount, double balance) {
    if (amount == 0 && balance == 0) return const SizedBox.shrink();
    return Row(
      children: [
        Text('$label: ',
            style: TextStyle(fontSize: 11, color: Theme.of(c).hintColor)),
        Text(money(amount),
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
        const Spacer(),
        Text(signedMoney(balance),
            style: TextStyle(fontSize: 11, color: Theme.of(c).hintColor)),
      ],
    );
  }
}
