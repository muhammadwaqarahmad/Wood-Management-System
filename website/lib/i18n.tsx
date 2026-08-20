"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

export type Lang = "en" | "ur";

// Labels copied 1:1 from the desktop app (timber/i18n.py) so the nav matches.
const DICT: Record<Lang, Record<string, string>> = {
  en: {
    // sections
    nav_dashboard: "Dashboard", nav_entry: "Entry", nav_money: "Money",
    nav_ledgers: "Ledgers", nav_manage: "Manage", nav_settings: "Settings",
    // items
    dashboard: "Dashboard", reports: "Reports",
    trade: "Buy & Sell", trades: "Trades", payment: "Payment", search: "Search",
    bank_accounts: "Bank Accounts", bank_book: "Bank Book", transfers: "Transfers",
    expenses: "Expenses", cheques: "Cheques", loans: "Loans",
    financial_position: "Financial Position", party_ledger: "Supplier Ledger",
    factory_ledger: "Factory Ledger", factory_sub_ledger: "Factory Sub-Ledger",
    trade_ledger: "Trade Ledger", profit_ledger: "Profit Ledger",
    overdue_report: "Overdue", aging: "Aging report",
    master_data: "Master Data", settings: "Settings",
    // chrome
    logout: "Log out", soon: "soon", theme: "Theme", language: "Language",
    account: "Account",
    export_pdf: "Export PDF", export_excel: "Export Excel",
  },
  ur: {
    nav_dashboard: "ڈیش بورڈ", nav_entry: "اندراج", nav_money: "رقم",
    nav_ledgers: "کھاتے", nav_manage: "انتظام", nav_settings: "ترتیبات",
    dashboard: "ڈیش بورڈ", reports: "رپورٹس",
    trade: "خرید و فروخت", trades: "سودے", payment: "ادائیگی", search: "تلاش",
    bank_accounts: "بینک اکاؤنٹس", bank_book: "بینک بک", transfers: "منتقلی",
    expenses: "اخراجات", cheques: "چیک", loans: "قرض",
    financial_position: "مالی پوزیشن", party_ledger: "بیوپاری کھاتہ",
    factory_ledger: "فیکٹری کھاتہ", factory_sub_ledger: "فیکٹری ذیلی کھاتہ",
    trade_ledger: "سودوں کا کھاتہ", profit_ledger: "منافع کھاتہ",
    overdue_report: "واجب الادا", aging: "عمر کے مطابق رپورٹ",
    master_data: "بنیادی ڈیٹا", settings: "ترتیبات",
    logout: "لاگ آؤٹ", soon: "جلد", theme: "تھیم", language: "زبان",
    account: "اکاؤنٹ",
    export_pdf: "پی ڈی ایف", export_excel: "ایکسل",
  },
};

type LangContextValue = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string) => string;
};

const LangContext = createContext<LangContextValue | null>(null);

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  useEffect(() => {
    const saved = (localStorage.getItem("asw_lang") as Lang) || "en";
    setLangState(saved);
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ur" ? "rtl" : "ltr";
  }, [lang]);

  function setLang(l: Lang) {
    localStorage.setItem("asw_lang", l);
    setLangState(l);
  }

  function t(key: string): string {
    return DICT[lang][key] ?? DICT.en[key] ?? key;
  }

  return (
    <LangContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LangContext.Provider>
  );
}

export function useLang(): LangContextValue {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error("useLang must be used inside <LangProvider>");
  return ctx;
}
