import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/models.dart';
import '../format.dart';
import '../i18n.dart';
import '../state/providers.dart';
import '../theme.dart';
import '../widgets/error_view.dart';
import 'party_ledger_screen.dart';

/// A searchable list of suppliers or factories with their balances.
/// kind = 'supplier' | 'factory'.
class PartiesTab extends ConsumerStatefulWidget {
  const PartiesTab({super.key, required this.kind});
  final String kind;

  @override
  ConsumerState<PartiesTab> createState() => _PartiesTabState();
}

class _PartiesTabState extends ConsumerState<PartiesTab> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(partiesProvider(widget.kind));
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
          child: TextField(
            decoration: InputDecoration(
              hintText:
                  '${tr(context, 'search')} ${tr(context, widget.kind == 'factory' ? 'factories' : 'suppliers')}',
              prefixIcon: const Icon(Icons.search),
              isDense: true,
            ),
            onChanged: (v) => setState(() => _query = v.trim().toLowerCase()),
          ),
        ),
        Expanded(
          child: async.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => ErrorView(
              message: e.toString(),
              onRetry: () => ref.invalidate(partiesProvider(widget.kind)),
            ),
            data: (list) {
              final filtered = _query.isEmpty
                  ? list
                  : list.where((p) => p.name.toLowerCase().contains(_query)).toList();
              if (filtered.isEmpty) {
                return Center(child: Text(tr(context, 'no_matches')));
              }
              return RefreshIndicator(
                onRefresh: () async => ref.invalidate(partiesProvider(widget.kind)),
                child: ListView.separated(
                  itemCount: filtered.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) => _PartyRow(party: filtered[i]),
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _PartyRow extends StatelessWidget {
  const _PartyRow({required this.party});
  final PartyBalance party;

  @override
  Widget build(BuildContext context) {
    // Positive = they owe us / we're owed; show the magnitude with a hint colour.
    final owed = party.balance != 0;
    final color = party.balance > 0 ? AppTheme.good : AppTheme.bad;
    return ListTile(
      title: Text(party.name),
      trailing: Text(
        signedMoney(party.balance),
        style: TextStyle(
          fontWeight: FontWeight.w700,
          color: owed ? color : Theme.of(context).hintColor,
        ),
      ),
      onTap: () => Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => PartyLedgerScreen(partyId: party.id, name: party.name),
      )),
    );
  }
}

/// Full-screen wrapper around [PartiesTab] so the Ledgers hub can push it as
/// "Supplier Ledger" / "Factory Ledger".
class PartiesScreen extends StatelessWidget {
  const PartiesScreen({super.key, required this.kind, required this.title});
  final String kind;
  final String title;
  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(title)),
        body: PartiesTab(kind: kind),
      );
}
