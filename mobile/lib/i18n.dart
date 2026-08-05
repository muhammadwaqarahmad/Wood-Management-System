import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'auth/secure_store.dart';

/// App language (English + Urdu), persisted, drives MaterialApp.locale.
/// Urdu automatically renders right-to-left via flutter_localizations.
class LocaleController extends StateNotifier<Locale> {
  LocaleController() : super(const Locale('en')) {
    _load();
  }
  final _store = SecureStore();

  Future<void> _load() async {
    final c = await _store.lang();
    if (c == 'ur') state = const Locale('ur');
  }

  Future<void> setLang(String code) async {
    state = Locale(code);
    await _store.saveLang(code);
  }
}

final localeProvider =
    StateNotifierProvider<LocaleController, Locale>((ref) => LocaleController());

const supportedLocales = [Locale('en'), Locale('ur')];

/// Translate [key] into the language currently active in [context].
/// Falls back to English, then to the key itself.
String tr(BuildContext context, String key) {
  final code = Localizations.localeOf(context).languageCode;
  final e = _t[key];
  if (e == null) return key;
  return (code == 'ur' ? e.$2 : e.$1);
}

/// (english, urdu) for every user-facing string in the app.
const Map<String, (String, String)> _t = {
  // --- navigation / tabs ---
  'nav_home': ('Home', 'ہوم'),
  'dashboard': ('Dashboard', 'ڈیش بورڈ'),
  'reports': ('Reports', 'رپورٹس'),
  'ledgers': ('Ledgers', 'کھاتے'),
  'money': ('Money', 'رقم'),
  'trades': ('Trades', 'سودے'),
  'entry': ('Entry', 'اندراج'),
  'manage': ('Manage', 'انتظام'),
  'view_only_companion': ('View-only companion', 'صرف دیکھنے کی ایپ'),
  'money_section': ('Money section', 'رقم سیکشن'),
  'ledgers_section': ('Ledgers section', 'کھاتے سیکشن'),

  // --- pages ---
  'new_trade': ('New Trade', 'نیا سودا'),
  'payments': ('Payments', 'ادائیگیاں'),
  'daily_book': ('Daily Book', 'روزنامچہ'),
  'search': ('Search', 'تلاش'),
  'overdue': ('Overdue', 'واجب الادا'),
  'aging': ('Aging', 'بقایا مدت'),
  'wood_summary': ('Wood Summary', 'لکڑی کا خلاصہ'),
  'master_data': ('Master Data', 'بنیادی ڈیٹا'),
  'settings': ('Settings', 'ترتیبات'),

  // --- login ---
  'sign_in': ('Sign in', 'سائن اِن'),
  'username': ('Username', 'صارف نام'),
  'password': ('Password', 'پاس ورڈ'),
  'set_server': ('Set server address', 'سرور ایڈریس درج کریں'),
  'server': ('Server', 'سرور'),
  'signed_in_as': ('Signed in as', 'بطور سائن ان'),
  'unlock_with': ('Unlock with', 'ان لاک کریں بذریعہ'),
  'unlock': ('Unlock', 'ان لاک'),
  'unlocking': ('Unlocking…', 'ان لاک ہو رہا ہے…'),
  'use_password': ('Use password instead', 'پاس ورڈ استعمال کریں'),
  'server_address': ('Server address', 'سرور ایڈریس'),
  'server_help': (
    'The address of the office server running the app\'s API. Example: http://192.168.10.35:8000',
    'دفتری سرور کا ایڈریس جہاں ایپ کا API چل رہا ہے۔ مثال: http://192.168.10.35:8000'
  ),
  'server_set_to': ('Server set to', 'سرور مقرر ہوا'),

  // --- settings ---
  'account': ('Account', 'اکاؤنٹ'),
  'appearance': ('Appearance', 'ظاہری شکل'),
  'system': ('System', 'سسٹم'),
  'light': ('Light', 'روشن'),
  'dark': ('Dark', 'گہرا'),
  'language': ('Language', 'زبان'),
  'security': ('Security', 'سیکیورٹی'),
  'session_security': ('Session security', 'سیشن سیکیورٹی'),
  'session_security_sub': (
    'Your login is stored in the device\'s secure keystore. The password is never saved on the phone.',
    'آپ کا لاگ اِن ڈیوائس کے محفوظ کی اسٹور میں رکھا جاتا ہے۔ پاس ورڈ فون پر کبھی محفوظ نہیں ہوتا۔'
  ),
  'connection': ('Connection', 'کنکشن'),
  'sign_out': ('Sign out', 'سائن آؤٹ'),
  'not_set': ('Not set', 'مقرر نہیں'),
  'not_available_device': ('Not available on this device', 'اس ڈیوائس پر دستیاب نہیں'),
  'biometric_unlock': ('Biometric unlock', 'بایومیٹرک ان لاک'),
  'unlock_suffix': ('unlock', 'ان لاک'),
  'bio_on_sub': (
    'On — open the app without typing your password',
    'آن — پاس ورڈ لکھے بغیر ایپ کھولیں'
  ),
  'bio_off_sub': (
    'Off — you type your password each time',
    'آف — آپ ہر بار پاس ورڈ لکھتے ہیں'
  ),

  // --- dashboard ---
  'period_summary': ('Period summary', 'مدت کا خلاصہ'),
  'financial_position': ('Financial position', 'مالی حیثیت'),
  'sale_bill': ('Sale bill', 'فروخت بل'),
  'purchase_bill': ('Purchase bill', 'خرید بل'),
  'profit': ('Profit', 'منافع'),
  'business_expenses': ('Business expenses', 'کاروباری اخراجات'),
  'house_expenses': ('House expenses', 'گھریلو اخراجات'),
  'banks': ('Banks', 'بینک'),
  'cash': ('Cash', 'نقد'),
  'to_receive': ('To receive', 'وصول طلب'),
  'to_give': ('To give', 'قابل ادائیگی'),
  'available': ('Available', 'دستیاب'),
  'unclaimed': ('Unclaimed', 'غیر مختص'),
  'loans_taken': ('Loans taken', 'لیے گئے قرض'),
  'loans_given': ('Loans given', 'دیے گئے قرض'),
  'sales_purchases': ('Sales & Purchases', 'فروخت و خرید'),
  'profit_expenses': ('Profit & Expenses', 'منافع و اخراجات'),
  'summary': ('Summary', 'خلاصہ'),
  'expenses_word': ('Expenses', 'اخراجات'),
  'bank_balances': ('Bank balances', 'بینک بیلنس'),
  'show_more': ('Show more', 'مزید دیکھیں'),
  'show_less': ('Show less', 'کم دیکھیں'),

  // --- reports ---
  'cash_flow': ('Cash flow', 'نقدی بہاؤ'),
  'factories': ('Factories', 'فیکٹریاں'),
  'suppliers': ('Suppliers', 'بیوپاری'),
  'factory': ('Factory', 'فیکٹری'),
  'supplier': ('Supplier', 'بیوپاری'),
  'total_sales': ('Total sales', 'کل فروخت'),
  'total_purchases': ('Total purchases', 'کل خرید'),
  'overdue_30': ('Overdue 30d', 'واجب الادا ۳۰ دن'),
  'overdue_60': ('Overdue 60d', 'واجب الادا ۶۰ دن'),
  'name': ('Name', 'نام'),
  'balance': ('Balance', 'بیلنس'),
  'sales': ('Sales', 'فروخت'),
  'purchases': ('Purchases', 'خرید'),
  'no_data_period': ('No data for this period', 'اس مدت کا کوئی ڈیٹا نہیں'),

  // --- payments ---
  'add_payment': ('Add Payment', 'ادائیگی شامل کریں'),
  'no_payments': ('No payments recorded', 'کوئی ادائیگی درج نہیں'),
  'total': ('Total', 'کل'),
  'reference': ('Ref', 'حوالہ'),
  'method_cash': ('Cash', 'نقد'),
  'method_cheque': ('Cheque', 'چیک'),
  'method_online': ('Online', 'آن لائن'),
  'method_bank': ('Bank', 'بینک'),

  // --- master data ---
  'wood_types': ('Wood Types', 'لکڑی کی اقسام'),
  'wood_type': ('Wood type', 'لکڑی کی قسم'),
  'bought_kg': ('Bought (kg)', 'خرید (کلو)'),
  'sold_kg': ('Sold (kg)', 'فروخت (کلو)'),
  'no_trade_data': ('No trade data yet', 'ابھی کوئی سودا ڈیٹا نہیں'),
  'add': ('Add', 'شامل کریں'),
  'none_yet': ('None yet', 'ابھی کچھ نہیں'),
  'no_wood_types': ('No wood types', 'کوئی لکڑی کی قسم نہیں'),
  'active': ('Active', 'فعال'),
  'inactive': ('Inactive', 'غیر فعال'),
  'status': ('Status', 'حیثیت'),
  'no_rates_set': ('No rates set', 'کوئی ریٹ مقرر نہیں'),

  // --- overdue / aging ---
  'overdue_factories': ('Overdue factories', 'واجب الادا فیکٹریاں'),
  'nothing_overdue': ('Nothing overdue', 'کچھ واجب الادا نہیں'),
  'no_receivables': ('No outstanding receivables', 'کوئی وصول طلب رقم نہیں'),

  // --- daily book ---
  'no_entries_day': ('No entries on this day', 'اس دن کوئی اندراج نہیں'),
  'purchase': ('Purchase', 'خرید'),
  'sale': ('Sale', 'فروخت'),
  'payment': ('Payment', 'ادائیگی'),

  // --- search ---
  'search_hint': ('Search parties, trades, payments…', 'پارٹیاں، سودے، ادائیگیاں تلاش کریں…'),
  'search_prompt': ('Type to search across everything.', 'تلاش کے لیے لکھیں۔'),
  'no_matches': ('No matches', 'کوئی نتیجہ نہیں'),

  // --- money ---
  'bank_accounts': ('Bank Accounts', 'بینک اکاؤنٹس'),
  'bank_book': ('Bank Book', 'بینک بک'),
  'transfers': ('Transfers', 'منتقلی'),
  'expenses': ('Expenses', 'اخراجات'),
  'cheques': ('Cheques', 'چیک'),
  'loans': ('Loans', 'قرضے'),
  'in': ('IN', 'آمد'),
  'out': ('OUT', 'روانگی'),
  'no_transactions': ('No transactions', 'کوئی لین دین نہیں'),
  'sub_bank_accounts': ('Every account with its balance', 'ہر اکاؤنٹ اور اس کا بیلنس'),
  'sub_bank_book': ('A running statement per account', 'ہر اکاؤنٹ کا رواں گوشوارہ'),
  'sub_transfers': ('Money moved between accounts', 'اکاؤنٹس کے درمیان منتقلی'),
  'sub_expenses': ('Business & house expenses', 'کاروباری و گھریلو اخراجات'),
  'sub_cheques': ('Pending, cleared and bounced', 'زیر التوا، کلیئر اور باؤنس'),
  'sub_loans': ('Loans taken and given', 'لیے اور دیے گئے قرض'),
  'sub_financial_position': ('Bank, cash, receivable, payable', 'بینک، نقد، وصول طلب، قابل ادائیگی'),
  'sub_supplier_ledger': ('A supplier\'s full statement', 'بیوپاری کا مکمل گوشوارہ'),
  'sub_factory_ledger': ('A factory\'s full statement', 'فیکٹری کا مکمل گوشوارہ'),
  'sub_trade_ledger': ('All trades with running totals', 'تمام سودے اور رواں میزان'),
  'sub_profit_ledger': ('Profit per trade', 'فی سودا منافع'),

  // --- ledgers ---
  'financial_position_page': ('Financial Position', 'مالی حیثیت'),
  'supplier_ledger': ('Supplier Ledger', 'بیوپاری کھاتہ'),
  'factory_ledger': ('Factory Ledger', 'فیکٹری کھاتہ'),
  'trade_ledger': ('Trade Ledger', 'سودا کھاتہ'),
  'profit_ledger': ('Profit Ledger', 'منافع کھاتہ'),
  'factory_subledger': ('Factory Sub-ledger', 'فیکٹری ذیلی کھاتہ'),
  'sub_factory_subledger': ('Weekly / irregular split per factory', 'ہر فیکٹری کی ہفتہ وار تقسیم'),

  // --- common ---
  'view_only': ('View only', 'صرف دیکھیں'),
  'save_trade': ('Save Trade', 'سودا محفوظ کریں'),
  'trade_desktop_note': (
    'Trades are entered on the desktop app. This screen is view-only.',
    'سودے ڈیسک ٹاپ ایپ پر درج ہوتے ہیں۔ یہ اسکرین صرف دیکھنے کے لیے ہے۔'
  ),
  'view_only_msg': (
    'View only — add or edit on the desktop app.',
    'صرف دیکھنے کے لیے — اندراج یا تبدیلی ڈیسک ٹاپ ایپ پر کریں۔'
  ),
  'could_not_load': ('Could not load', 'لوڈ نہیں ہو سکا'),
  'retry': ('Retry', 'دوبارہ کوشش'),
  'cancel': ('Cancel', 'منسوخ'),
  'save': ('Save', 'محفوظ کریں'),

  // --- money / ledger detail screens ---
  'total_available': ('Total available', 'کل دستیاب'),
  'no_transfers': ('No transfers', 'کوئی منتقلی نہیں'),
  'total_expenses': ('Total expenses', 'کل اخراجات'),
  'no_expenses': ('No expenses', 'کوئی اخراجات نہیں'),
  'pending': ('Pending', 'زیر التوا'),
  'cleared': ('Cleared', 'کلیئر'),
  'bounced': ('Bounced', 'باؤنس'),
  'all': ('All', 'تمام'),
  'no_cheques': ('No cheques', 'کوئی چیک نہیں'),
  'no_loans': ('No loans', 'کوئی قرض نہیں'),
  'taken': ('Taken', 'لیا'),
  'given': ('Given', 'دیا'),
  'bank': ('Bank', 'بینک'),
  'total_to_receive': ('Total to receive', 'کل وصول طلب'),
  'total_to_give': ('Total to give', 'کل قابل ادائیگی'),
  'nothing_here': ('Nothing here', 'یہاں کچھ نہیں'),
  'bank_cash_total': ('Bank + cash total', 'بینک + نقد کل'),
  'no_entries': ('No entries', 'کوئی اندراج نہیں'),
  'split_rate': ('Split rate', 'تقسیم ریٹ'),
  'weekly': ('Weekly', 'ہفتہ وار'),
  'irregular': ('Irregular', 'غیر باقاعدہ'),
  'load': ('Load', 'لوڈ'),
  'no_trades_period': ('No trades in this period', 'اس مدت میں کوئی سودا نہیں'),
  'date': ('Date', 'تاریخ'),
  'wood': ('Wood', 'لکڑی'),
  'buy': ('Buy', 'خرید'),
  'sell': ('Sell', 'فروخت'),
  'margin': ('Margin', 'مارجن'),
  'no_trades_yet': ('No trades yet', 'ابھی کوئی سودا نہیں'),
  'no_transactions_yet': ('No transactions yet', 'ابھی کوئی لین دین نہیں'),
  'settled': ('Settled', 'ادا شدہ'),
  'we_owe': ('We owe', 'ہم پر واجب'),
  'advance_with_them': ('Advance with them', 'ان کے پاس ایڈوانس'),
  'they_owe_us': ('They owe us', 'ان پر ہمارا واجب'),
  'we_owe_them': ('We owe them', 'ہم پر ان کا واجب'),
};
