// Models for the Ledgers section (Financial Position, Trade Ledger, Profit
// Ledger, Factory Sub-ledger). Kept separate from models.dart for clarity.

class FinancialPosition {
  FinancialPosition({
    required this.bankTotal,
    required this.cashBalance,
    required this.chequeTotal,
    required this.unclaimedTotal,
    required this.grandTotal,
    required this.totalReceivable,
    required this.totalPayable,
    required this.accounts,
    required this.receivables,
    required this.payables,
  });
  final double bankTotal, cashBalance, chequeTotal, unclaimedTotal, grandTotal;
  final double totalReceivable, totalPayable;
  final List<AccountRow> accounts;
  final List<PositionParty> receivables;
  final List<PositionParty> payables;

  factory FinancialPosition.fromJson(Map<String, dynamic> j) {
    double d(String k) => (j[k] as num?)?.toDouble() ?? 0;
    return FinancialPosition(
      bankTotal: d('bank_total'),
      cashBalance: d('cash_balance'),
      chequeTotal: d('cheque_total'),
      unclaimedTotal: d('unclaimed_total'),
      grandTotal: d('grand_total'),
      totalReceivable: d('total_receivable'),
      totalPayable: d('total_payable'),
      accounts: ((j['accounts'] as List?) ?? [])
          .map((a) => AccountRow.fromJson(a as Map<String, dynamic>))
          .toList(),
      receivables: ((j['receivables'] as List?) ?? [])
          .map((r) => PositionParty.fromJson(r as Map<String, dynamic>))
          .toList(),
      payables: ((j['payables'] as List?) ?? [])
          .map((r) => PositionParty.fromJson(r as Map<String, dynamic>))
          .toList(),
    );
  }
}

class AccountRow {
  AccountRow({required this.id, required this.name, required this.closing, required this.isCash});
  final int id;
  final String name;
  final double closing;
  final bool isCash;
  factory AccountRow.fromJson(Map<String, dynamic> j) => AccountRow(
        id: j['id'] as int,
        name: j['name'] as String,
        closing: (j['closing'] as num).toDouble(),
        isCash: j['is_cash'] as bool? ?? false,
      );
}

class PositionParty {
  PositionParty({required this.name, required this.contact, required this.kind, required this.amount});
  final String name;
  final String contact;
  final String kind;
  final double amount;
  factory PositionParty.fromJson(Map<String, dynamic> j) => PositionParty(
        name: j['name'] as String,
        contact: (j['contact'] ?? '') as String,
        kind: (j['kind'] ?? '') as String,
        amount: (j['amount'] as num).toDouble(),
      );
}

class TradeLedger {
  TradeLedger({required this.purchase, required this.sale, required this.profit, required this.rows});
  final double purchase, sale, profit;
  final List<TradeLedgerRow> rows;
  factory TradeLedger.fromJson(Map<String, dynamic> j) {
    final t = j['totals'] as Map<String, dynamic>;
    double d(String k) => (t[k] as num?)?.toDouble() ?? 0;
    return TradeLedger(
      purchase: d('purchase'),
      sale: d('sale'),
      profit: d('profit'),
      rows: ((j['rows'] as List?) ?? [])
          .map((r) => TradeLedgerRow.fromJson(r as Map<String, dynamic>))
          .toList(),
    );
  }
}

class TradeLedgerRow {
  TradeLedgerRow({
    required this.date,
    required this.vehicle,
    required this.wood,
    required this.weightText,
    required this.supplierName,
    required this.buyRate,
    required this.purchaseBill,
    required this.supplierStatus,
    required this.factoryName,
    required this.sellRate,
    required this.saleBill,
    required this.factoryStatus,
    required this.profit,
  });
  final String date, vehicle, wood, weightText;
  final String supplierName, supplierStatus, factoryName, factoryStatus;
  final double buyRate, purchaseBill, sellRate, saleBill, profit;
  factory TradeLedgerRow.fromJson(Map<String, dynamic> j) {
    double d(String k) => (j[k] as num?)?.toDouble() ?? 0;
    return TradeLedgerRow(
      date: j['txn_date'] as String,
      vehicle: (j['vehicle'] ?? '') as String,
      wood: (j['wood'] ?? '') as String,
      weightText: (j['weight_text'] ?? '') as String,
      supplierName: (j['supplier_name'] ?? '') as String,
      buyRate: d('buy_rate'),
      purchaseBill: d('purchase_bill'),
      supplierStatus: (j['supplier_status'] ?? '') as String,
      factoryName: (j['factory_name'] ?? '') as String,
      sellRate: d('sell_rate'),
      saleBill: d('sale_bill'),
      factoryStatus: (j['factory_status'] ?? '') as String,
      profit: d('profit'),
    );
  }
}

class ProfitLedger {
  ProfitLedger({
    required this.profit,
    required this.sale,
    required this.purchase,
    required this.trades,
    required this.marginPct,
    required this.rows,
  });
  final double profit, sale, purchase, marginPct;
  final int trades;
  final List<ProfitRow> rows;
  factory ProfitLedger.fromJson(Map<String, dynamic> j) {
    final t = j['totals'] as Map<String, dynamic>;
    double d(String k) => (t[k] as num?)?.toDouble() ?? 0;
    return ProfitLedger(
      profit: d('profit'),
      sale: d('sale'),
      purchase: d('purchase'),
      trades: (t['trades'] as num?)?.toInt() ?? 0,
      marginPct: d('margin_pct'),
      rows: ((j['rows'] as List?) ?? [])
          .map((r) => ProfitRow.fromJson(r as Map<String, dynamic>))
          .toList(),
    );
  }
}

class ProfitRow {
  ProfitRow({
    required this.date,
    required this.bapariName,
    required this.factoryName,
    required this.weight,
    required this.bapariRate,
    required this.factoryRate,
    required this.purchase,
    required this.sale,
    required this.profit,
  });
  final String date, bapariName, factoryName;
  final double weight, bapariRate, factoryRate, purchase, sale, profit;
  factory ProfitRow.fromJson(Map<String, dynamic> j) {
    double d(String k) => (j[k] as num?)?.toDouble() ?? 0;
    return ProfitRow(
      date: j['txn_date'] as String,
      bapariName: (j['bapari_name'] ?? '') as String,
      factoryName: (j['factory_name'] ?? '') as String,
      weight: d('weight'),
      bapariRate: d('bapari_rate'),
      factoryRate: d('factory_rate'),
      purchase: d('purchase'),
      sale: d('sale'),
      profit: d('profit'),
    );
  }
}

class FactorySplit {
  FactorySplit({
    required this.factoryName,
    required this.splitRate,
    required this.closingLeft,
    required this.closingRight,
    required this.closingTotal,
    required this.entries,
  });
  final String factoryName;
  final double splitRate, closingLeft, closingRight, closingTotal;
  final List<SplitEntry> entries;
  factory FactorySplit.fromJson(Map<String, dynamic> j) {
    double d(String k) => (j[k] as num?)?.toDouble() ?? 0;
    return FactorySplit(
      factoryName: (j['factory_name'] ?? '') as String,
      splitRate: d('split_rate'),
      closingLeft: d('closing_left'),
      closingRight: d('closing_right'),
      closingTotal: d('closing_total'),
      entries: ((j['entries'] as List?) ?? [])
          .map((e) => SplitEntry.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

class SplitEntry {
  SplitEntry({
    required this.date,
    required this.kind,
    required this.vehicle,
    required this.wood,
    required this.leftNet,
    required this.leftPayment,
    required this.leftBalance,
    required this.rightAmount,
    required this.rightPayment,
    required this.rightBalance,
    required this.detail,
  });
  final String date, kind, vehicle, wood, detail;
  final double leftNet, leftPayment, leftBalance, rightAmount, rightPayment, rightBalance;
  bool get isPayment => kind == 'payment';
  factory SplitEntry.fromJson(Map<String, dynamic> j) {
    double d(String k) => (j[k] as num?)?.toDouble() ?? 0;
    return SplitEntry(
      date: j['txn_date'] as String,
      kind: (j['kind'] ?? '') as String,
      vehicle: (j['vehicle'] ?? '') as String,
      wood: (j['wood'] ?? '') as String,
      leftNet: d('left_net'),
      leftPayment: d('left_payment'),
      leftBalance: d('left_balance'),
      rightAmount: d('right_amount'),
      rightPayment: d('right_payment'),
      rightBalance: d('right_balance'),
      detail: (j['detail'] ?? '') as String,
    );
  }
}
