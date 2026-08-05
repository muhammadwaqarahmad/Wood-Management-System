import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../api/payments_models.dart';
import '../i18n.dart';
import '../state/providers.dart';
import '../theme.dart';

/// Global search — parties, purchases, sales and payments — mirroring the
/// desktop search screen. Read-only: results are informational only.
class SearchScreen extends ConsumerStatefulWidget {
  const SearchScreen({super.key});
  @override
  ConsumerState<SearchScreen> createState() => _SearchScreenState();
}

class _SearchScreenState extends ConsumerState<SearchScreen> {
  final _controller = TextEditingController();
  String _query = '';
  Timer? _debounce;

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String v) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () {
      if (mounted) setState(() => _query = v.trim());
    });
  }

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(searchProvider(_query));
    return Scaffold(
      appBar: AppBar(
        title: TextField(
          controller: _controller,
          autofocus: true,
          textInputAction: TextInputAction.search,
          onChanged: _onChanged,
          onSubmitted: (v) => setState(() => _query = v.trim()),
          decoration: InputDecoration(
            hintText: tr(context, 'search_hint'),
            border: InputBorder.none,
            suffixIcon: _controller.text.isEmpty
                ? null
                : IconButton(
                    icon: const Icon(Icons.clear),
                    onPressed: () {
                      _controller.clear();
                      setState(() => _query = '');
                    },
                  ),
          ),
        ),
      ),
      body: _query.isEmpty
          ? _hint(context, tr(context, 'search_prompt'))
          : async.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => _hint(context, '${tr(context, 'could_not_load')}\n$e'),
              data: (rows) {
                if (rows.isEmpty) {
                  return _hint(context, '${tr(context, 'no_matches')} “$_query”');
                }
                return ListView.separated(
                  itemCount: rows.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) => _tile(context, rows[i]),
                );
              },
            ),
    );
  }

  Widget _tile(BuildContext context, SearchHit h) {
    final meta = <String>[
      if (h.date.isNotEmpty) h.date,
      if (h.detail.isNotEmpty) h.detail,
    ].join(' · ');
    return ListTile(
      leading: _kindBadge(h.kind),
      title: Text(h.name, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: meta.isEmpty
          ? null
          : Text(meta, maxLines: 1, overflow: TextOverflow.ellipsis),
      trailing: h.amount.isEmpty
          ? null
          : Text(h.amount, style: const TextStyle(fontWeight: FontWeight.w700)),
    );
  }

  Widget _kindBadge(String kind) {
    final (IconData icon, Color color) = switch (kind) {
      'party' => (Icons.person, AppTheme.tone('indigo')),
      'purchase' => (Icons.shopping_cart, AppTheme.tone('sky')),
      'sale' => (Icons.sell, AppTheme.tone('emerald')),
      'payment' => (Icons.payments, AppTheme.tone('amber')),
      _ => (Icons.circle, AppTheme.tone('slate')),
    };
    return CircleAvatar(
      radius: 18,
      backgroundColor: color.withValues(alpha: 0.14),
      child: Icon(icon, size: 18, color: color),
    );
  }

  Widget _hint(BuildContext context, String text) => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Text(text,
              textAlign: TextAlign.center,
              style: TextStyle(color: Theme.of(context).hintColor)),
        ),
      );
}
