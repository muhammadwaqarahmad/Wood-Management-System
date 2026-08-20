"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop BankBookScreen (timber/ui/screens/bank_book_screen.py):
   account + view (Daily summary / Statement) + period filters, four KPI tiles
   (Opening / In / Out / Closing), the two tables, and PDF/Excel export. Both
   views arrive in one call so switching is instant. */

type Account = { id: number; name: string };
type Entry = {
  entry_date: string; description: string; source: string; destination: string;
  money_in: number; money_out: number; balance: number;
};
type Daily = { day: string; opening: number; money_in: number; money_out: number; closing: number };
type Book = {
  account_name: string; opening: number; closing: number;
  total_in: number; total_out: number; entries: Entry[]; daily: Daily[];
};

const VIEWS = [{ v: "daily", label: "Daily summary" }, { v: "statement", label: "Statement" }];
const PERIODS = [
  { v: "day", label: "Day" }, { v: "week", label: "Week" }, { v: "month", label: "Month" },
  { v: "year", label: "Year" }, { v: "custom", label: "Custom range" }, { v: "all", label: "All" },
];
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);

// Local-date ISO (never via UTC — avoids an off-by-one on midnight-constructed dates).
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function rangeQS(p: string, from: string, to: string): string {
  const t = new Date(); const Y = t.getFullYear(); const M = t.getMonth();
  if (p === "day") return `&start=${iso(t)}&end=${iso(t)}`;
  if (p === "week") {
    const dow = (t.getDay() + 6) % 7;               // Monday = 0, like the desktop
    const s = new Date(Y, M, t.getDate() - dow);
    const e = new Date(s); e.setDate(s.getDate() + 6);
    return `&start=${iso(s)}&end=${iso(e)}`;
  }
  if (p === "month") return `&start=${iso(new Date(Y, M, 1))}&end=${iso(new Date(Y, M + 1, 0))}`;
  if (p === "year") return `&start=${iso(new Date(Y, 0, 1))}&end=${iso(new Date(Y, 11, 31))}`;
  if (p === "custom") return `&start=${from}&end=${to}`;
  return "";
}

function Tile({ label, value, color, icon }: { label: string; value: number | null; color: string; icon: string }) {
  return (
    <div className="tile" style={{ borderLeftColor: color }}>
      <div className="cap">
        <span className="chip" style={{ background: `linear-gradient(135deg, ${color}, color-mix(in srgb, ${color} 60%, #fff))` }}>
          <Icon name={icon} size={16} />
        </span>
        {label}
      </div>
      <div className="val">{value === null ? "—" : money(value)}</div>
    </div>
  );
}

export default function BankBookPage() {
  const toast = useToast();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState<number | "">("");
  const [view, setView] = useState("daily");
  const [period, setPeriod] = useState("day");
  const [from, setFrom] = useState(() => iso(new Date()));
  const [to, setTo] = useState(() => iso(new Date()));
  const [book, setBook] = useState<Book | null>(null);
  const [q, setQ] = useState("");
  const [expOpen, setExpOpen] = useState(false);
  const expRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) { if (expRef.current && !expRef.current.contains(e.target as Node)) setExpOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const accs = await api.get<Account[]>("/money/accounts?include_inactive=true");
        const sorted = accs.slice().sort((a, b) => a.name.localeCompare(b.name));
        setAccounts(sorted);
        if (sorted.length) setAccountId(sorted[0].id);
      } catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
    })();
  }, [toast]);

  const load = useCallback(async () => {
    if (!accountId) { setBook(null); return; }
    try {
      setBook(await api.get<Book>(`/money/accounts/${accountId}/book?_=1${rangeQS(period, from, to)}`));
    } catch (e) { toast.error(errMsg(e, "Couldn't load the book.")); }
  }, [accountId, period, from, to, toast]);
  useEffect(() => { load(); }, [load]);

  async function doExport(fmt: "pdf" | "xlsx") {
    setExpOpen(false);
    if (!accountId) { toast.warning("Choose an account first."); return; }
    try { await api.download(`/money/accounts/${accountId}/book/export?fmt=${fmt}&view=${view}${rangeQS(period, from, to)}`, `bank_book.${fmt}`); }
    catch (e) { toast.error(errMsg(e, "Export failed.")); }
  }

  const isDaily = view === "daily";
  // Tile figures follow the desktop: the daily view carries only a closing;
  // the statement view shows the running opening/closing and period totals.
  const tiles = useMemo(() => {
    if (!book) return { opening: null as number | null, in: 0, out: 0, closing: 0 };
    if (isDaily) {
      const inSum = book.daily.reduce((s, r) => s + r.money_in, 0);
      const outSum = book.daily.reduce((s, r) => s + r.money_out, 0);
      const closing = book.daily.length ? book.daily[book.daily.length - 1].closing : 0;
      return { opening: null, in: inSum, out: outSum, closing };
    }
    return { opening: book.opening, in: book.total_in, out: book.total_out, closing: book.closing };
  }, [book, isDaily]);

  const stmtRows = book && q
    ? book.entries.filter((e) => [e.entry_date, e.source, e.destination, e.description]
        .some((v) => (v || "").toLowerCase().includes(q.toLowerCase())))
    : book?.entries ?? [];

  return (
    <div>
      <div className="toolbar" style={{ flexWrap: "wrap", alignItems: "center" }}>
        <span className="tb-lbl">Bank Accounts:</span>
        <select className="input" style={{ maxWidth: 220 }} value={accountId} onChange={(e) => setAccountId(Number(e.target.value) || "")}>
          <option value="">— choose account —</option>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>

        <span className="tb-lbl">Show:</span>
        <select className="input" style={{ maxWidth: 170 }} value={view} onChange={(e) => setView(e.target.value)}>
          {VIEWS.map((v) => <option key={v.v} value={v.v}>{v.label}</option>)}
        </select>

        <span className="tb-lbl">Period:</span>
        <select className="input" style={{ maxWidth: 160 }} value={period} onChange={(e) => setPeriod(e.target.value)}>
          {PERIODS.map((p) => <option key={p.v} value={p.v}>{p.label}</option>)}
        </select>
        {period === "custom" && (
          <>
            <input className="input" type="date" style={{ maxWidth: 165 }} value={from} onChange={(e) => setFrom(e.target.value)} />
            <input className="input" type="date" style={{ maxWidth: 165 }} value={to} onChange={(e) => setTo(e.target.value)} />
          </>
        )}

        <div style={{ flex: 1 }} />
        <div className="manage" ref={expRef}>
          <button className="btn" onClick={() => setExpOpen((o) => !o)}><Icon name="download" size={15} /> Export ▾</button>
          {expOpen && (
            <div className="manage-menu">
              <button className="manage-item" onClick={() => doExport("pdf")}><Icon name="download" size={16} /> PDF</button>
              <button className="manage-item" onClick={() => doExport("xlsx")}><Icon name="download" size={16} /> Excel</button>
            </div>
          )}
        </div>
      </div>

      <div className="tiles" style={{ margin: "12px 0" }}>
        <Tile label="Opening" value={tiles.opening} color="#64748b" icon="book-open" />
        <Tile label="In" value={tiles.in} color="#10b981" icon="trending-up" />
        <Tile label="Out" value={tiles.out} color="#f43f5e" icon="trending-down" />
        <Tile label="Closing" value={tiles.closing} color="#6366f1" icon="wallet" />
      </div>

      {!isDaily && (
        <div className="md-bar">
          <div className="search-wrap"><Icon name="search" size={16} /><input className="input" placeholder="Search statement" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        </div>
      )}

      <div className="tbl-wrap">
        {isDaily ? (
          <table className="tbl">
            <thead><tr>
              <th style={{ textAlign: "left" }}>Date</th>
              <th className="right">Opening</th><th className="right">In</th>
              <th className="right">Out</th><th className="right">Closing</th>
            </tr></thead>
            <tbody>
              {(!book || book.daily.length === 0) && <tr><td colSpan={5} className="empty">No movements.</td></tr>}
              {book?.daily.map((r) => (
                <tr key={r.day}>
                  <td>{r.day}</td>
                  <td className="right">{money(r.opening)}</td>
                  <td className="right">{money(r.money_in)}</td>
                  <td className="right">{money(r.money_out)}</td>
                  <td className="right">{money(r.closing)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="tbl">
            <thead><tr>
              <th style={{ textAlign: "left" }}>Date</th><th style={{ textAlign: "left" }}>From</th>
              <th style={{ textAlign: "left" }}>To</th><th className="right">In</th>
              <th className="right">Out</th><th className="right">Balance</th>
            </tr></thead>
            <tbody>
              {stmtRows.length === 0 && <tr><td colSpan={6} className="empty">No movements.</td></tr>}
              {stmtRows.map((e, i) => (
                <tr key={i}>
                  <td>{e.entry_date}</td>
                  <td>{e.source || "—"}</td>
                  <td>{e.destination || "—"}</td>
                  <td className="right" style={{ color: e.money_in ? "var(--pos)" : "var(--muted)" }}>{e.money_in ? money(e.money_in) : ""}</td>
                  <td className="right" style={{ color: e.money_out ? "var(--neg)" : "var(--muted)" }}>{e.money_out ? money(e.money_out) : ""}</td>
                  <td className="right">{money(e.balance)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
