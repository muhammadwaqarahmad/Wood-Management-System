import 'package:intl/intl.dart';

final _grouped = NumberFormat('#,##0', 'en');

/// Rupee amount with comma grouping, e.g. 1234567 -> "1,234,567".
String money(num v) => _grouped.format(v.round());

/// Signed money for balances: negative shown in parentheses like the desktop.
String signedMoney(num v) =>
    v < 0 ? '(${_grouped.format(v.abs().round())})' : _grouped.format(v.round());
