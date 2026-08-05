import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../format.dart';
import '../i18n.dart';
import '../state/providers.dart';
import '../theme.dart';

/// Daily Book (روزنامچہ) — every purchase, sale and payment on a chosen day.
/// Mirrors the desktop daily book. Read-only.
class DailyBookScreen extends ConsumerStatefulWidget {
  const DailyBookScreen({super.key});
  @override
  ConsumerState<DailyBookScreen> createState() => _DailyBookScreenState();
}

class _DailyBookScreenState extends ConsumerState<DailyBookScreen> {
  DateTime _day = DateTime.now();

  String get _iso =>
      '${_day.year.toString().padLeft(4, '0')}-${_day.month.toString().padLeft(2, '0')}-${_day.day.toString().padLeft(2, '0')}';

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _day,
      firstDate: DateTime(2018),
      lastDate: DateTime.now().add(const Duration(days: 1)),
    );
    if (picked != null) setState(() => _day = picked);
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(dailyBookProvider(_iso));
    return Scaffold(
      appBar: AppBar(
        title: Text(tr(context, 'daily_book')),
        actions: [
          TextButton.icon(
            onPressed: _pickDate,
            icon: const Icon(Icons.calendar_today, size: 16, color: Colors.white),
            label: Text(_iso, style: const TextStyle(color: Colors.white)),
          ),
        ],
      ),
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
            return Center(child: Text(tr(context, 'no_entries_day')));
          }
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(dailyBookProvider(_iso)),
            child: ListView.separated(
              itemCount: rows.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (_, i) {
                final e = rows[i];
                final (IconData icon, Color color) = _kindStyle(e.kind);
                return ListTile(
                  leading: CircleAvatar(
                    backgroundColor: color.withValues(alpha: 0.14),
                    child: Icon(icon, size: 20, color: color),
                  ),
                  title: Text(e.partyName, maxLines: 1, overflow: TextOverflow.ellipsis),
                  subtitle: Text('${e.kind}${e.detail.isEmpty ? '' : ' · ${e.detail}'}',
                      maxLines: 1, overflow: TextOverflow.ellipsis),
                  trailing: Text(money(e.amount),
                      style: TextStyle(fontWeight: FontWeight.w700, color: color)),
                );
              },
            ),
          );
        },
      ),
    );
  }

  (IconData, Color) _kindStyle(String kind) {
    final k = kind.toLowerCase();
    if (k.startsWith('purchase')) return (Icons.shopping_cart, AppTheme.tone('sky'));
    if (k.startsWith('sale')) return (Icons.sell, AppTheme.tone('emerald'));
    if (k.contains('in')) return (Icons.south_west, AppTheme.good);
    if (k.contains('out')) return (Icons.north_east, AppTheme.bad);
    return (Icons.payments, AppTheme.tone('amber'));
  }
}
