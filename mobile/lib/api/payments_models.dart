// Models for the Payments page and global Search (both read-only).

double _d(Map<String, dynamic> j, String k) => (j[k] as num?)?.toDouble() ?? 0;
String _s(Map<String, dynamic> j, String k) => (j[k] ?? '') as String;

/// One saved payment (money paid to a supplier / received from a factory).
class PaymentRecord {
  PaymentRecord({
    required this.id,
    required this.date,
    required this.partyName,
    required this.amount,
    required this.method,
    required this.accountName,
    required this.partyAccount,
    required this.reference,
  });
  final int id;
  final String date, partyName, method, accountName, partyAccount, reference;
  final double amount;

  factory PaymentRecord.fromJson(Map<String, dynamic> j) => PaymentRecord(
        id: j['id'] as int,
        date: _s(j, 'txn_date'),
        partyName: _s(j, 'party_name'),
        amount: _d(j, 'amount'),
        method: _s(j, 'method'),
        accountName: _s(j, 'account_name'),
        partyAccount: _s(j, 'party_account'),
        reference: _s(j, 'reference'),
      );
}

/// One global-search hit. `kind` is party | purchase | sale | payment.
class SearchHit {
  SearchHit({
    required this.kind,
    required this.date,
    required this.name,
    required this.detail,
    required this.amount,
  });
  final String kind, date, name, detail, amount;

  factory SearchHit.fromJson(Map<String, dynamic> j) => SearchHit(
        kind: _s(j, 'kind'),
        date: _s(j, 'date'),
        name: _s(j, 'name'),
        detail: _s(j, 'detail'),
        amount: _s(j, 'amount'),
      );
}
