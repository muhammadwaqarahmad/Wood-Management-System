import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../format.dart';
import '../i18n.dart';
import '../state/providers.dart';
import '../theme.dart';

/// Aging report — factory receivables split into 0-30 / 31-60 / 61-90 / 90+
/// day buckets. Mirrors the desktop Aging screen. Read-only.
class AgingScreen extends ConsumerWidget {
  const AgingScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(agingProvider);
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'aging'))),
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
            return Center(child: Text(tr(context, 'no_receivables')));
          }
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(agingProvider),
            child: ListView.separated(
              itemCount: rows.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (_, i) {
                final r = rows[i];
                return Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            child: Text(r.name,
                                style: const TextStyle(fontWeight: FontWeight.w700),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis),
                          ),
                          Text(money(r.total),
                              style: const TextStyle(fontWeight: FontWeight.w800)),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Row(children: [
                        _bucket(context, '0-30', r.b0_30, AppTheme.good),
                        _bucket(context, '31-60', r.b31_60, AppTheme.tone('amber')),
                        _bucket(context, '61-90', r.b61_90, AppTheme.warn),
                        _bucket(context, '90+', r.b90p, AppTheme.bad),
                      ]),
                    ],
                  ),
                );
              },
            ),
          );
        },
      ),
    );
  }

  Widget _bucket(BuildContext c, String label, double value, Color color) => Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label,
                style: TextStyle(
                    fontSize: 10, letterSpacing: 0.5, color: Theme.of(c).hintColor)),
            const SizedBox(height: 2),
            Text(value == 0 ? '—' : money(value),
                style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: value == 0 ? Theme.of(c).hintColor : color)),
          ],
        ),
      );
}
