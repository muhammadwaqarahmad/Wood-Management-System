import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../format.dart';
import '../../i18n.dart';
import '../../state/providers.dart';
import '../../widgets/error_view.dart';

class TransfersScreen extends ConsumerWidget {
  const TransfersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    const (String?, String?) key = (null, null);
    final async = ref.watch(transfersProvider(key));
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'transfers'))),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(
            message: e.toString(), onRetry: () => ref.invalidate(transfersProvider(key))),
        data: (rows) => rows.isEmpty
            ? Center(child: Text(tr(context, 'no_transfers')))
            : RefreshIndicator(
                onRefresh: () async => ref.invalidate(transfersProvider(key)),
                child: ListView.separated(
                  itemCount: rows.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) {
                    final t = rows[i];
                    return ListTile(
                      leading: const Icon(Icons.swap_horiz),
                      title: Text('${t.fromName}  →  ${t.toName}',
                          maxLines: 1, overflow: TextOverflow.ellipsis),
                      subtitle: Text(t.note.isEmpty ? t.date : '${t.date} · ${t.note}'),
                      trailing: Text(money(t.amount),
                          style: const TextStyle(fontWeight: FontWeight.w700)),
                    );
                  },
                ),
              ),
      ),
    );
  }
}
