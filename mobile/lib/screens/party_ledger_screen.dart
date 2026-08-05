import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../format.dart';
import '../i18n.dart';
import '../state/providers.dart';
import '../theme.dart';
import '../widgets/error_view.dart';

/// One party's running statement — every load and payment, with the balance
/// after each line. Pushed from the parties list.
class PartyLedgerScreen extends ConsumerWidget {
  const PartyLedgerScreen({super.key, required this.partyId, required this.name});
  final int partyId;
  final String name;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(partyLedgerProvider(partyId));
    return Scaffold(
      appBar: AppBar(title: Text(name)),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
          message: e.toString(),
          onRetry: () => ref.invalidate(partyLedgerProvider(partyId)),
        ),
        data: (st) => _StatementBody(statement: st),
      ),
    );
  }
}

class _StatementBody extends StatelessWidget {
  const _StatementBody({required this.statement});
  final LedgerStatement statement;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _ClosingHeader(closing: statement.closing, type: statement.partyType),
        Expanded(
          child: statement.entries.isEmpty
              ? Center(child: Text(tr(context, 'no_transactions_yet')))
              : ListView.separated(
                  itemCount: statement.entries.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) => _EntryRow(entry: statement.entries[i]),
                ),
        ),
      ],
    );
  }
}

class _ClosingHeader extends StatelessWidget {
  const _ClosingHeader({required this.closing, required this.type});
  final double closing;
  final String type;

  @override
  Widget build(BuildContext context) {
    // A supplier balance > 0 means WE owe them; a factory > 0 means THEY owe us.
    final supplier = type == 'bapari';
    final label = closing == 0
        ? tr(context, 'settled')
        : supplier
            ? tr(context, closing > 0 ? 'we_owe' : 'advance_with_them')
            : tr(context, closing > 0 ? 'they_owe_us' : 'we_owe_them');
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
          Text(signedMoney(closing),
              style: const TextStyle(
                  fontSize: 26, fontWeight: FontWeight.w800, color: AppTheme.accent)),
        ],
      ),
    );
  }
}

class _EntryRow extends StatelessWidget {
  const _EntryRow({required this.entry});
  final LedgerEntry entry;

  @override
  Widget build(BuildContext context) {
    final isPay = entry.isPayment;
    final amount = isPay ? entry.credit : entry.debit;
    return ListTile(
      dense: true,
      leading: Icon(
        isPay ? Icons.south_west : Icons.local_shipping_outlined,
        color: isPay ? AppTheme.good : AppTheme.accent,
        size: 20,
      ),
      title: Text(entry.description, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(entry.date),
      trailing: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Text((isPay ? '- ' : '+ ') + money(amount),
              style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: isPay ? AppTheme.good : null)),
          Text(signedMoney(entry.balance),
              style: TextStyle(fontSize: 12, color: Theme.of(context).hintColor)),
        ],
      ),
    );
  }
}
