import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../format.dart';
import '../i18n.dart';
import '../state/providers.dart';
import '../theme.dart';

/// Overdue report — factories past their credit period, worst first.
/// Mirrors the desktop Overdue screen. Read-only.
class OverdueScreen extends ConsumerWidget {
  const OverdueScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(overdueProvider);
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'overdue'))),
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
            return Center(child: Text('${tr(context, 'nothing_overdue')} 🎉'));
          }
          final total = rows.fold<double>(0, (s, r) => s + r.outstanding);
          return Column(children: [
            Container(
              width: double.infinity,
              color: AppTheme.bad.withValues(alpha: 0.08),
              padding: const EdgeInsets.all(16),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  _stat(context, tr(context, 'overdue_factories'), '${rows.length}', null),
                  _stat(context, tr(context, 'total'), money(total), AppTheme.bad),
                ],
              ),
            ),
            Expanded(
              child: RefreshIndicator(
                onRefresh: () async => ref.invalidate(overdueProvider),
                child: ListView.separated(
                  itemCount: rows.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) {
                    final r = rows[i];
                    return ListTile(
                      leading: CircleAvatar(
                        backgroundColor: AppTheme.bad.withValues(alpha: 0.12),
                        child: Text('${r.daysOverdue}',
                            style: const TextStyle(
                                fontWeight: FontWeight.w800,
                                fontSize: 13,
                                color: AppTheme.bad)),
                      ),
                      title: Text(r.name, maxLines: 1, overflow: TextOverflow.ellipsis),
                      subtitle: Text(
                          'Oldest ${r.oldestDate} · ${r.daysOutstanding}d old · '
                          '${r.creditDays}d terms'),
                      trailing: Text(money(r.outstanding),
                          style: const TextStyle(
                              fontWeight: FontWeight.w700, color: AppTheme.bad)),
                    );
                  },
                ),
              ),
            ),
          ]);
        },
      ),
    );
  }

  Widget _stat(BuildContext c, String label, String value, Color? color) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: TextStyle(
                  fontSize: 10, letterSpacing: 1, color: Theme.of(c).hintColor)),
          const SizedBox(height: 2),
          Text(value,
              style: TextStyle(
                  fontSize: 18, fontWeight: FontWeight.w800, color: color)),
        ],
      );
}
