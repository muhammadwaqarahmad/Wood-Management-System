// The dashboard/reports period filter — identical logic to the desktop:
// All time / Today / This month / This year / Custom.

enum PeriodKind { all, day, month, year, custom }

class Period {
  const Period(this.kind, {this.from, this.to});
  final PeriodKind kind;
  final DateTime? from; // custom only
  final DateTime? to;

  static const initial = Period(PeriodKind.day); // opens on Today, like desktop

  String _iso(DateTime d) =>
      '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  /// (start, end) as ISO strings or null (null = open-ended = all time).
  (String?, String?) range() {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    switch (kind) {
      case PeriodKind.day:
        return (_iso(today), _iso(today));
      case PeriodKind.month:
        return (_iso(DateTime(today.year, today.month, 1)), _iso(today));
      case PeriodKind.year:
        return (_iso(DateTime(today.year, 1, 1)), _iso(today));
      case PeriodKind.custom:
        return (from != null ? _iso(from!) : null, to != null ? _iso(to!) : null);
      case PeriodKind.all:
        return (null, null);
    }
  }

  static const labels = {
    PeriodKind.all: 'All',
    PeriodKind.day: 'Today',
    PeriodKind.month: 'Month',
    PeriodKind.year: 'Year',
    PeriodKind.custom: 'Custom',
  };
}
