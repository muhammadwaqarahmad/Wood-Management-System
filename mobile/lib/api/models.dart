// Plain data models mirroring the API's JSON. Money arrives as numbers.

class AppUser {
  AppUser({required this.id, required this.username, required this.role, this.name});
  final int id;
  final String username;
  final String role;
  final String? name;

  factory AppUser.fromJson(Map<String, dynamic> j) => AppUser(
        id: j['id'] as int,
        username: j['username'] as String,
        role: j['role'] as String,
        name: j['name'] as String?,
      );
}

/// Full dashboard summary — every card, the summary table, chart series and
/// bank balances (mirrors the desktop dashboard exactly).
class DashboardData {
  DashboardData({required this.cards, required this.table, required this.series, required this.banks});

  final Map<String, double> cards; // all card values by key
  final List<SummaryRow> table; // plus/minus summary rows
  final List<SeriesPoint> series; // chart buckets
  final List<BankBalance> banks;

  double card(String k) => cards[k] ?? 0;
  int get tradesCount => (cards['trades'] ?? 0).round();

  factory DashboardData.fromJson(Map<String, dynamic> j) {
    final c = (j['cards'] as Map<String, dynamic>);
    final cards = <String, double>{
      for (final e in c.entries) e.key: (e.value as num?)?.toDouble() ?? 0,
    };
    return DashboardData(
      cards: cards,
      table: ((j['table'] as List?) ?? [])
          .map((r) => SummaryRow.fromJson(r as Map<String, dynamic>))
          .toList(),
      series: ((j['series'] as List?) ?? [])
          .map((s) => SeriesPoint.fromJson(s as Map<String, dynamic>))
          .toList(),
      banks: ((j['banks'] as List?) ?? [])
          .map((b) => BankBalance.fromJson(b as Map<String, dynamic>))
          .toList(),
    );
  }
}

/// One row of the plus/minus summary table. sign: +1 adds, -1 subtracts, 0 = result.
class SummaryRow {
  SummaryRow({required this.key, required this.amount, required this.sign});
  final String key;
  final double amount;
  final int sign;
  factory SummaryRow.fromJson(Map<String, dynamic> j) => SummaryRow(
        key: j['key'] as String,
        amount: (j['amount'] as num).toDouble(),
        sign: (j['sign'] as num).toInt(),
      );
}

/// One chart bucket (day/month/year) with the four series.
class SeriesPoint {
  SeriesPoint(
      {required this.label,
      required this.sales,
      required this.purchases,
      required this.profit,
      required this.expenses});
  final String label;
  final double sales, purchases, profit, expenses;
  factory SeriesPoint.fromJson(Map<String, dynamic> j) {
    double d(String k) => (j[k] as num?)?.toDouble() ?? 0;
    return SeriesPoint(
        label: j['label'] as String,
        sales: d('sales'),
        purchases: d('purchases'),
        profit: d('profit'),
        expenses: d('expenses'));
  }
}

class BankBalance {
  BankBalance({required this.name, required this.balance});
  final String name;
  final double balance;
  factory BankBalance.fromJson(Map<String, dynamic> j) =>
      BankBalance(name: j['name'] as String, balance: (j['balance'] as num).toDouble());
}

class PartyBalance {
  PartyBalance({required this.id, required this.name, required this.balance});
  final int id;
  final String name;
  final double balance;
  factory PartyBalance.fromJson(Map<String, dynamic> j) => PartyBalance(
        id: j['id'] as int,
        name: j['name'] as String,
        balance: (j['balance'] as num).toDouble(),
      );
}

// ---------------------------------------------------------------- ledger
class LedgerStatement {
  LedgerStatement({
    required this.partyName,
    required this.partyType,
    required this.opening,
    required this.closing,
    required this.entries,
  });
  final String partyName;
  final String partyType;
  final double opening;
  final double closing;
  final List<LedgerEntry> entries;

  factory LedgerStatement.fromJson(Map<String, dynamic> j) => LedgerStatement(
        partyName: (j['party'] as Map)['name'] as String,
        partyType: (j['party'] as Map)['type'] as String,
        opening: (j['opening'] as num).toDouble(),
        closing: (j['closing'] as num).toDouble(),
        entries: ((j['entries'] as List?) ?? [])
            .map((e) => LedgerEntry.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class LedgerEntry {
  LedgerEntry({
    required this.date,
    required this.kind,
    required this.description,
    required this.debit,
    required this.credit,
    required this.balance,
  });
  final String date;
  final String kind; // 'txn' (load) | 'payment'
  final String description;
  final double debit;
  final double credit;
  final double balance;

  bool get isPayment => kind == 'payment';

  factory LedgerEntry.fromJson(Map<String, dynamic> j) => LedgerEntry(
        date: j['date'] as String,
        kind: j['kind'] as String,
        description: j['description'] as String,
        debit: (j['debit'] as num).toDouble(),
        credit: (j['credit'] as num).toDouble(),
        balance: (j['balance'] as num).toDouble(),
      );
}

// ---------------------------------------------------------------- trades
class TradesPage {
  TradesPage({required this.totalCount, required this.profit, required this.trades});
  final int totalCount;
  final double profit;
  final List<Trade> trades;

  factory TradesPage.fromJson(Map<String, dynamic> j) {
    final totals = j['totals'];
    // trades_totals returns (profit, sale_bill, muds) as a list
    final profit = (totals is List && totals.isNotEmpty)
        ? (totals[0] as num).toDouble()
        : 0.0;
    return TradesPage(
      totalCount: (j['total_count'] as num?)?.toInt() ?? 0,
      profit: profit,
      trades: ((j['trades'] as List?) ?? [])
          .map((e) => Trade.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class Trade {
  Trade({
    required this.id,
    required this.date,
    required this.wood,
    required this.bapariName,
    required this.factoryName,
    required this.muds,
    required this.kg,
    required this.purchaseBill,
    required this.saleBill,
    required this.profit,
    required this.vehicle,
  });
  final int id;
  final String date;
  final String wood;
  final String bapariName;
  final String factoryName;
  final double muds;
  final double kg;
  final double purchaseBill;
  final double saleBill;
  final double profit;
  final String vehicle;

  factory Trade.fromJson(Map<String, dynamic> j) {
    double d(String k) => (j[k] as num?)?.toDouble() ?? 0;
    return Trade(
      id: j['id'] as int,
      date: j['txn_date'] as String,
      wood: (j['wood'] ?? '') as String,
      bapariName: (j['bapari_name'] ?? '') as String,
      factoryName: (j['factory_name'] ?? '') as String,
      muds: d('muds'),
      kg: d('kg'),
      purchaseBill: d('purchase_bill'),
      saleBill: d('sale_bill'),
      profit: d('profit'),
      vehicle: (j['vehicle'] ?? '') as String,
    );
  }
}

// -------------------------------------------------------- reports: cash flow
class CashflowReport {
  CashflowReport({required this.worth, required this.rows});
  final double worth;
  final List<CashflowRow> rows;
  factory CashflowReport.fromJson(Map<String, dynamic> j) => CashflowReport(
        worth: (j['worth'] as num).toDouble(),
        rows: ((j['rows'] as List?) ?? [])
            .map((r) => CashflowRow.fromJson(r as Map<String, dynamic>))
            .toList(),
      );
}

class CashflowRow {
  CashflowRow(
      {required this.key, required this.amount, required this.sign, required this.section});
  final String key;
  final double amount;
  final int sign;
  final String section;
  factory CashflowRow.fromJson(Map<String, dynamic> j) => CashflowRow(
        key: j['key'] as String,
        amount: (j['amount'] as num).toDouble(),
        sign: (j['sign'] as num).toInt(),
        section: j['section'] as String,
      );
}

// ----------------------------------------------------- reports: party stats
class PartyStats {
  PartyStats({required this.overall, required this.rows});
  final Map<String, double> overall;
  final List<PartyStatRow> rows;
  double o(String k) => overall[k] ?? 0;
  int get trades => (overall['trades'] ?? 0).round();

  factory PartyStats.fromJson(Map<String, dynamic> j) {
    final ov = j['overall'] as Map<String, dynamic>;
    return PartyStats(
      overall: {for (final e in ov.entries) e.key: (e.value as num?)?.toDouble() ?? 0},
      rows: ((j['rows'] as List?) ?? [])
          .map((r) => PartyStatRow.fromJson(r as Map<String, dynamic>))
          .toList(),
    );
  }
}

class PartyStatRow {
  PartyStatRow({
    required this.name,
    required this.trades,
    required this.volume,
    required this.profit,
    required this.balance,
    required this.over30,
    required this.over60,
  });
  final String name;
  final int trades;
  final double volume, profit, balance, over30, over60;
  factory PartyStatRow.fromJson(Map<String, dynamic> j) {
    double d(String k) => (j[k] as num?)?.toDouble() ?? 0;
    return PartyStatRow(
      name: j['name'] as String,
      trades: (j['trades'] as num).toInt(),
      volume: d('volume'),
      profit: d('profit'),
      balance: d('balance'),
      over30: d('over30'),
      over60: d('over60'),
    );
  }
}
