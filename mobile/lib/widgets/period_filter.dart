import 'package:flutter/material.dart';

import '../period.dart';

/// The period filter used by Dashboard and Reports: a compact pill row
/// (All / Today / Month / Year / Custom). Picking Custom opens a date-range
/// picker; the chosen range shows under the pills.
class PeriodFilter extends StatelessWidget {
  const PeriodFilter({super.key, required this.period, required this.onChanged});
  final Period period;
  final ValueChanged<Period> onChanged;

  Future<void> _pickCustom(BuildContext context) async {
    final now = DateTime.now();
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime(now.year - 5),
      lastDate: now,
      initialDateRange: (period.from != null && period.to != null)
          ? DateTimeRange(start: period.from!, end: period.to!)
          : DateTimeRange(start: now.subtract(const Duration(days: 30)), end: now),
    );
    if (picked != null) {
      onChanged(Period(PeriodKind.custom, from: picked.start, to: picked.end));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final k in PeriodKind.values)
                Padding(
                  padding: const EdgeInsets.only(right: 6),
                  child: _Pill(
                    label: Period.labels[k]!,
                    selected: period.kind == k,
                    onTap: () {
                      if (k == PeriodKind.custom) {
                        _pickCustom(context);
                      } else {
                        onChanged(Period(k));
                      }
                    },
                  ),
                ),
            ],
          ),
        ),
        if (period.kind == PeriodKind.custom && period.from != null)
          Padding(
            padding: const EdgeInsets.only(top: 8, left: 2),
            child: Text(
              '${_d(period.from!)}  →  ${_d(period.to!)}',
              style: TextStyle(fontSize: 12, color: Theme.of(context).hintColor),
            ),
          ),
      ],
    );
  }

  String _d(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}

class _Pill extends StatelessWidget {
  const _Pill({required this.label, required this.selected, required this.onTap});
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final primary = Theme.of(context).colorScheme.primary;
    return Material(
      color: selected ? primary : Theme.of(context).cardColor,
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        borderRadius: BorderRadius.circular(20),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
                color: selected ? primary : Theme.of(context).dividerColor),
          ),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: selected ? Colors.white : null,
            ),
          ),
        ),
      ),
    );
  }
}
