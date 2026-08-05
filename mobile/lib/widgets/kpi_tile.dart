import 'package:flutter/material.dart';

import '../format.dart';
import '../theme.dart';

/// The dashboard/reports KPI card: tinted icon chip + label + value, with a
/// coloured accent bar down the leading edge — matching the desktop tiles.
class KpiTile extends StatelessWidget {
  const KpiTile({
    super.key,
    required this.icon,
    required this.label,
    required this.value,
    this.tone = 'slate',
    this.signed = false,
    this.plain = false,
    this.rawValue,
  });

  final IconData icon;
  final String label;
  final double value;
  final String tone;
  final bool signed; // colour by sign
  final bool plain; // show as integer count, not money
  final String? rawValue; // override the displayed text

  @override
  Widget build(BuildContext context) {
    final accent = AppTheme.tone(tone);
    final text = rawValue ?? (plain ? value.toInt().toString() : signedMoney(value));
    final valueColor = signed ? AppTheme.amount(context, value) : null;
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(16),
        border: Border(left: BorderSide(color: accent, width: 4)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 12,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      padding: const EdgeInsets.fromLTRB(8, 7, 8, 7),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Container(
                width: 16,
                height: 16,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: accent.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(5),
                ),
                child: Icon(icon, size: 10, color: accent),
              ),
              const SizedBox(width: 5),
              Expanded(
                child: Text(
                  label.toUpperCase(),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 8,
                    height: 1.05,
                    fontWeight: FontWeight.w700,
                    color: Theme.of(context).hintColor,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          // Shrink to fit the narrow (4-per-row) tile instead of truncating,
          // so the full number always shows.
          Align(
            alignment: Alignment.centerLeft,
            child: FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(
                text,
                maxLines: 1,
                style: TextStyle(
                    fontSize: 13, fontWeight: FontWeight.w800, color: valueColor),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
