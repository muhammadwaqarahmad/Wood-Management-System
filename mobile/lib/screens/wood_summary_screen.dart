import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../format.dart';
import '../i18n.dart';
import '../state/providers.dart';
import '../widgets/lazy_table.dart';

/// Wood summary — total weight bought vs sold per wood type. Read-only,
/// uses the shared virtualized [LazyTable].
class WoodSummaryScreen extends ConsumerWidget {
  const WoodSummaryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(woodSummaryProvider);
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'wood_summary'))),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text('Could not load.\n$e',
                textAlign: TextAlign.center,
                style: TextStyle(color: Theme.of(context).hintColor)),
          ),
        ),
        data: (rows) {
          if (rows.isEmpty) {
            return Center(child: Text(tr(context, 'no_trade_data')));
          }
          return Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: LazyTable(
              columns: [
                TableCol(tr(context, 'wood_type'), 170),
                TableCol(tr(context, 'bought_kg'), 120, numeric: true),
                TableCol(tr(context, 'sold_kg'), 120, numeric: true),
              ],
              rowCount: rows.length,
              onRefresh: () async => ref.invalidate(woodSummaryProvider),
              cellsBuilder: (i) {
                final w = rows[i];
                return [
                  Text(w.name, maxLines: 1, overflow: TextOverflow.ellipsis),
                  Text(money(w.boughtWeight)),
                  Text(money(w.soldWeight)),
                ];
              },
            ),
          );
        },
      ),
    );
  }
}
