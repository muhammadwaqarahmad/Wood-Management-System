import 'package:flutter/material.dart';

/// One label / sign / amount line in a summary or cash-flow statement.
class KvRow {
  const KvRow(this.label, this.amount,
      {this.sign, this.color, this.bold = false});
  final String label;
  final String amount;
  final String? sign; // '+', '−', '=' or null
  final Color? color;
  final bool bold;
}

/// Borderless rows table (Summary / Bank balances / cash-flow section) — the
/// same look as the desktop's _KVTable.
class KvTable extends StatelessWidget {
  const KvTable({super.key, required this.rows});
  final List<KvRow> rows;

  @override
  Widget build(BuildContext context) {
    final divider = Theme.of(context).dividerColor.withValues(alpha: 0.5);
    return Column(
      children: [
        for (final r in rows)
          Container(
            decoration: BoxDecoration(
              border: Border(bottom: BorderSide(color: divider)),
            ),
            padding: const EdgeInsets.symmetric(vertical: 9),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    r.label,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: r.bold ? FontWeight.w800 : FontWeight.w400,
                    ),
                  ),
                ),
                if (r.sign != null)
                  SizedBox(
                    width: 22,
                    child: Text(
                      r.sign!,
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 11, color: Theme.of(context).hintColor),
                    ),
                  ),
                Text(
                  r.amount,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w700,
                    color: r.color,
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }
}

/// A titled rounded panel, matching the desktop cards.
class SectionCard extends StatelessWidget {
  const SectionCard({super.key, required this.title, this.icon, required this.child});
  final String title;
  final IconData? icon;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(18, 16, 18, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                if (icon != null) ...[
                  Icon(icon, size: 17, color: Theme.of(context).colorScheme.primary),
                  const SizedBox(width: 8),
                ],
                Text(title,
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800)),
              ],
            ),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }
}
