import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../format.dart';
import '../i18n.dart';
import '../state/providers.dart';
import '../theme.dart';
import '../widgets/lazy_table.dart';
import '../widgets/read_only.dart';
import 'party_ledger_screen.dart';

/// Master Data — Suppliers, Factories and Wood Types, mirroring the desktop
/// manager. Read-only: rows open a ledger view; the Add button is inert.
/// Uses the same virtualized [LazyTable] as the Reports page.
class MasterDataScreen extends StatelessWidget {
  const MasterDataScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: AppBar(
          title: Text(tr(context, 'master_data')),
          bottom: TabBar(tabs: [
            Tab(text: tr(context, 'suppliers')),
            Tab(text: tr(context, 'factories')),
            Tab(text: tr(context, 'wood_types')),
          ]),
        ),
        floatingActionButton: DisabledFab(icon: Icons.add, label: tr(context, 'add')),
        body: const Padding(
          padding: EdgeInsets.symmetric(horizontal: 12),
          child: TabBarView(children: [
            _PartyTable(kind: 'supplier'),
            _PartyTable(kind: 'factory'),
            _WoodTypeTable(),
          ]),
        ),
      ),
    );
  }
}

class _PartyTable extends ConsumerWidget {
  const _PartyTable({required this.kind});
  final String kind;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(partiesProvider(kind));
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => _err(context, e),
      data: (rows) {
        if (rows.isEmpty) return Center(child: Text(tr(context, 'none_yet')));
        return LazyTable(
          columns: [
            TableCol(tr(context, 'name'), 240),
            TableCol(tr(context, 'balance'), 120, numeric: true),
          ],
          rowCount: rows.length,
          onRefresh: () async => ref.invalidate(partiesProvider(kind)),
          onRowTap: (i) => Navigator.of(context).push(MaterialPageRoute(
              builder: (_) =>
                  PartyLedgerScreen(partyId: rows[i].id, name: rows[i].name))),
          cellsBuilder: (i) {
            final p = rows[i];
            return [
              Text(p.name, maxLines: 1, overflow: TextOverflow.ellipsis),
              Text(signedMoney(p.balance),
                  style: TextStyle(
                      fontWeight: FontWeight.w600,
                      color: AppTheme.amount(context, p.balance))),
            ];
          },
        );
      },
    );
  }
}

class _WoodTypeTable extends ConsumerWidget {
  const _WoodTypeTable();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(woodTypesProvider);
    return async.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => _err(context, e),
      data: (rows) {
        if (rows.isEmpty) return Center(child: Text(tr(context, 'no_wood_types')));
        return LazyTable(
          columns: [
            TableCol(tr(context, 'name'), 170),
            TableCol(tr(context, 'supplier'), 110, numeric: true),
            TableCol(tr(context, 'factory'), 110, numeric: true),
            TableCol(tr(context, 'status'), 84),
          ],
          rowCount: rows.length,
          onRefresh: () async => ref.invalidate(woodTypesProvider),
          cellsBuilder: (i) {
            final w = rows[i];
            return [
              Text(w.name, maxLines: 1, overflow: TextOverflow.ellipsis),
              Text(w.supplierRate > 0 ? money(w.supplierRate) : '—'),
              Text(w.factoryRate > 0 ? money(w.factoryRate) : '—'),
              Text(tr(context, w.isActive ? 'active' : 'inactive'),
                  style: TextStyle(
                      fontSize: 12,
                      color: w.isActive
                          ? AppTheme.good
                          : Theme.of(context).hintColor)),
            ];
          },
        );
      },
    );
  }
}

Widget _err(BuildContext context, Object e) => Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Text('${tr(context, 'could_not_load')}\n$e',
            textAlign: TextAlign.center,
            style: TextStyle(color: Theme.of(context).hintColor)),
      ),
    );
