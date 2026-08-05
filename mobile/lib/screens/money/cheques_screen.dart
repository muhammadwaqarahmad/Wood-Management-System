import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../format.dart';
import '../../i18n.dart';
import '../../state/providers.dart';
import '../../theme.dart';
import '../../widgets/error_view.dart';

/// Cheques with a status filter (defaults to Pending, like the desktop).
class ChequesScreen extends ConsumerStatefulWidget {
  const ChequesScreen({super.key});
  @override
  ConsumerState<ChequesScreen> createState() => _ChequesScreenState();
}

class _ChequesScreenState extends ConsumerState<ChequesScreen> {
  String? _status = 'pending';
  static const _options = {
    'pending': 'pending',
    'cleared': 'cleared',
    'bounced': 'bounced',
    null: 'all',
  };

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(chequesProvider(_status));
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'cheques'))),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(10),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(children: [
                for (final e in _options.entries)
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: ChoiceChip(
                      label: Text(tr(context, e.value)),
                      selected: _status == e.key,
                      onSelected: (_) => setState(() => _status = e.key),
                    ),
                  ),
              ]),
            ),
          ),
          Expanded(
            child: async.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (err, _) => ErrorView(
                  message: err.toString(),
                  onRetry: () => ref.invalidate(chequesProvider(_status))),
              data: (rows) => rows.isEmpty
                  ? Center(child: Text(tr(context, 'no_cheques')))
                  : RefreshIndicator(
                      onRefresh: () async => ref.invalidate(chequesProvider(_status)),
                      child: ListView.separated(
                        itemCount: rows.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (_, i) {
                          final c = rows[i];
                          return ListTile(
                            leading: Icon(c.isIn ? Icons.south_west : Icons.north_east,
                                color: c.isIn ? AppTheme.good : AppTheme.bad),
                            title: Text(c.partyName),
                            subtitle: Text('${c.date} · ${c.accountName}'
                                '${c.reference.isNotEmpty ? ' · ${c.reference}' : ''}',
                                maxLines: 1, overflow: TextOverflow.ellipsis),
                            trailing: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                Text(money(c.amount),
                                    style: const TextStyle(fontWeight: FontWeight.w700)),
                                Text(c.status, style: TextStyle(fontSize: 11, color: Theme.of(context).hintColor)),
                              ],
                            ),
                          );
                        },
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}
