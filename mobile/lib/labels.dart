/// English labels for the report/dashboard keys (mirrors the desktop i18n
/// English strings). Bilingual Urdu can be added later.
const kLabels = {
  // summary / cash-flow row keys
  'banks': 'Banks',
  'cash': 'Cash',
  'available': 'Available',
  'total_available': 'Total available',
  'receivable': 'To receive',
  'to_receive': 'To receive',
  'loans_given': 'Loans given',
  'payable': 'To give',
  'to_give': 'To give',
  'loans': 'Loans taken',
  'loans_taken': 'Loans taken',
  'net_worth': 'Net position',
  'net_position': 'Net position',
  'cheques_in': 'Cheques in hand',
  'unclaimed': 'Unclaimed',
  'profit': 'Profit',
  'total_profit': 'Total profit',
  'exp_business': 'Business expenses',
  'exp_house': 'House expenses',
  'profit_after': 'Profit after expenses',
  // cash-flow section headings
  'position': 'Cash & bank',
  'balances': 'Receivable / payable',
  'cheques': 'Cheques',
  'flows': "Period's flows",
};

String label(String key) => kLabels[key] ?? key;
