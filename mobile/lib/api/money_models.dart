// Models for the Money section (accounts, bank book, transfers, expenses,
// cheques, loans).

double _d(Map<String, dynamic> j, String k) => (j[k] as num?)?.toDouble() ?? 0;
String _s(Map<String, dynamic> j, String k) => (j[k] ?? '') as String;

class BankAccount {
  BankAccount({
    required this.id,
    required this.name,
    required this.closing,
    required this.isCash,
    required this.isActive,
    this.bankName,
    this.accountNumber,
  });
  final int id;
  final String name;
  final double closing;
  final bool isCash;
  final bool isActive;
  final String? bankName;
  final String? accountNumber;
  factory BankAccount.fromJson(Map<String, dynamic> j) => BankAccount(
        id: j['id'] as int,
        name: j['name'] as String,
        closing: _d(j, 'closing'),
        isCash: j['is_cash'] as bool? ?? false,
        isActive: j['is_active'] as bool? ?? true,
        bankName: j['bank_name'] as String?,
        accountNumber: j['account_number'] as String?,
      );
}

class BankBook {
  BankBook({
    required this.accountName,
    required this.opening,
    required this.closing,
    required this.totalIn,
    required this.totalOut,
    required this.entries,
  });
  final String accountName;
  final double opening, closing, totalIn, totalOut;
  final List<BankEntry> entries;
  factory BankBook.fromJson(Map<String, dynamic> j) => BankBook(
        accountName: _s(j, 'account_name'),
        opening: _d(j, 'opening'),
        closing: _d(j, 'closing'),
        totalIn: _d(j, 'total_in'),
        totalOut: _d(j, 'total_out'),
        entries: ((j['entries'] as List?) ?? [])
            .map((e) => BankEntry.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}

class BankEntry {
  BankEntry({
    required this.date,
    required this.description,
    required this.source,
    required this.destination,
    required this.moneyIn,
    required this.moneyOut,
    required this.balance,
  });
  final String date, description, source, destination;
  final double moneyIn, moneyOut, balance;
  factory BankEntry.fromJson(Map<String, dynamic> j) => BankEntry(
        date: _s(j, 'entry_date'),
        description: _s(j, 'description'),
        source: _s(j, 'source'),
        destination: _s(j, 'destination'),
        moneyIn: _d(j, 'money_in'),
        moneyOut: _d(j, 'money_out'),
        balance: _d(j, 'balance'),
      );
}

class Transfer {
  Transfer({
    required this.date,
    required this.fromName,
    required this.toName,
    required this.amount,
    required this.note,
  });
  final String date, fromName, toName, note;
  final double amount;
  factory Transfer.fromJson(Map<String, dynamic> j) => Transfer(
        date: _s(j, 'txn_date'),
        fromName: _s(j, 'from_name'),
        toName: _s(j, 'to_name'),
        amount: _d(j, 'amount'),
        note: _s(j, 'note'),
      );
}

class Expense {
  Expense({
    required this.date,
    required this.kind,
    required this.category,
    required this.amount,
    required this.accountName,
    required this.note,
  });
  final String date, kind, category, accountName, note;
  final double amount;
  factory Expense.fromJson(Map<String, dynamic> j) => Expense(
        date: _s(j, 'txn_date'),
        kind: _s(j, 'kind'),
        category: _s(j, 'category'),
        amount: _d(j, 'amount'),
        accountName: _s(j, 'account_name'),
        note: _s(j, 'note'),
      );
}

class Cheque {
  Cheque({
    required this.date,
    required this.partyName,
    required this.direction,
    required this.amount,
    required this.accountName,
    required this.reference,
    required this.status,
  });
  final String date, partyName, direction, accountName, reference, status;
  final double amount;
  bool get isIn => direction == 'in';
  factory Cheque.fromJson(Map<String, dynamic> j) => Cheque(
        date: _s(j, 'txn_date'),
        partyName: _s(j, 'party_name'),
        direction: _s(j, 'direction'),
        amount: _d(j, 'amount'),
        accountName: _s(j, 'account_name'),
        reference: _s(j, 'reference'),
        status: _s(j, 'status'),
      );
}

class Loan {
  Loan({
    required this.date,
    required this.lenderName,
    required this.principal,
    required this.repaid,
    required this.outstanding,
    required this.accountName,
    required this.direction,
    this.expectedReturnDate,
  });
  final String date, lenderName, accountName, direction;
  final double principal, repaid, outstanding;
  final String? expectedReturnDate;
  bool get isTaken => direction == 'taken';
  factory Loan.fromJson(Map<String, dynamic> j) => Loan(
        date: _s(j, 'txn_date'),
        lenderName: _s(j, 'lender_name'),
        principal: _d(j, 'principal'),
        repaid: _d(j, 'repaid'),
        outstanding: _d(j, 'outstanding'),
        accountName: _s(j, 'account_name'),
        direction: _s(j, 'direction'),
        expectedReturnDate: j['expected_return_date'] as String?,
      );
}
