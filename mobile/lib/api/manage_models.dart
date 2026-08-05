// Models for the manage/report pages: wood types, overdue, aging.

double _d(Map<String, dynamic> j, String k) => (j[k] as num?)?.toDouble() ?? 0;
String _s(Map<String, dynamic> j, String k) => (j[k] ?? '') as String;

class WoodType {
  WoodType({
    required this.id,
    required this.name,
    required this.description,
    required this.supplierRate,
    required this.factoryRate,
    required this.isActive,
  });
  final int id;
  final String name, description;
  final double supplierRate, factoryRate;
  final bool isActive;
  factory WoodType.fromJson(Map<String, dynamic> j) => WoodType(
        id: j['id'] as int,
        name: _s(j, 'name'),
        description: _s(j, 'description'),
        supplierRate: _d(j, 'default_supplier_rate'),
        factoryRate: _d(j, 'default_factory_rate'),
        isActive: j['is_active'] as bool? ?? true,
      );
}

class OverdueFactory {
  OverdueFactory({
    required this.name,
    required this.outstanding,
    required this.oldestDate,
    required this.daysOutstanding,
    required this.creditDays,
    required this.daysOverdue,
  });
  final String name, oldestDate;
  final double outstanding;
  final int daysOutstanding, creditDays, daysOverdue;
  factory OverdueFactory.fromJson(Map<String, dynamic> j) => OverdueFactory(
        name: _s(j, 'name'),
        outstanding: _d(j, 'outstanding'),
        oldestDate: _s(j, 'oldest_date'),
        daysOutstanding: (j['days_outstanding'] as num?)?.toInt() ?? 0,
        creditDays: (j['credit_days'] as num?)?.toInt() ?? 0,
        daysOverdue: (j['days_overdue'] as num?)?.toInt() ?? 0,
      );
}

class AgingRow {
  AgingRow({
    required this.name,
    required this.b0_30,
    required this.b31_60,
    required this.b61_90,
    required this.b90p,
    required this.total,
  });
  final String name;
  final double b0_30, b31_60, b61_90, b90p, total;
  factory AgingRow.fromJson(Map<String, dynamic> j) => AgingRow(
        name: _s(j, 'name'),
        b0_30: _d(j, 'b0_30'),
        b31_60: _d(j, 'b31_60'),
        b61_90: _d(j, 'b61_90'),
        b90p: _d(j, 'b90p'),
        total: _d(j, 'total'),
      );
}

/// One line in the Daily Book: a purchase, sale or payment on a given day.
class DayEntry {
  DayEntry({
    required this.kind,
    required this.partyName,
    required this.detail,
    required this.amount,
  });
  final String kind, partyName, detail;
  final double amount;
  factory DayEntry.fromJson(Map<String, dynamic> j) => DayEntry(
        kind: _s(j, 'kind'),
        partyName: _s(j, 'party_name'),
        detail: _s(j, 'detail'),
        amount: _d(j, 'amount'),
      );
}

/// Weight bought vs sold per wood type.
class WoodSummary {
  WoodSummary({
    required this.name,
    required this.boughtWeight,
    required this.soldWeight,
  });
  final String name;
  final double boughtWeight, soldWeight;
  factory WoodSummary.fromJson(Map<String, dynamic> j) => WoodSummary(
        name: _s(j, 'name'),
        boughtWeight: _d(j, 'bought_weight'),
        soldWeight: _d(j, 'sold_weight'),
      );
}
