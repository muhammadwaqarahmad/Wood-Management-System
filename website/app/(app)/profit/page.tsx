"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop ProfitLedgerScreen (timber/ui/screens/profit_ledger_screen.py):
   every combined load with its margin — four headline cards (Total profit /
   Total sales / Total purchases / Avg margin), a show-limit + search, an 8-column
   table, and PDF/Excel export. No period filter (all-time), like the desktop. */

type Row = {
  id: number; txn_date: string; bapari_name: string; factory_name: string;
  weight: number; bapari_rate: number; factory_rate: number;
  profit: number; purchase: number; sale: number;
};
type Totals = { profit: number; sale: number; purchase: number; trades: number; margin_pct: number };

const LIMITS = [{ v: 200, label: "200" }, { v: 500, label: "500" }, { v: 1000, label: "1000" }, { v: 0, label: "All" }];
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);
// General number format (:g) — drop trailing zeros: 803.0 -> "803", 6.28 -> "6.28".
const g = (v: number) => String(parseFloat(v.toFixed(2)));
const rowMargin = (r: Row) => (r.sale ? (r.profit / r.sale) * 100 : 0);

function Card({ label, value, color, icon, sub }: { label: string; value: string; color: string; icon: string; sub?: string }) {
  return (
    <div className="tile" style={{ borderLeftColor: color }}>
      <div className="cap">
        <span className="chip" style={{ background: `linear-gradient(135deg, ${color}, color-mix(in srgb, ${color} 60%, #fff))` }}>
          <Icon name={icon} size={16} />
        </span>
        {label}
      </div>
      <div className="val" style={{ color }}>{value}</div>
      {sub && <div className="set-note" style={{ margin: "2px 0 0" }}>{sub}</div>}
    </div>
  );
}

export default function ProfitLedgerPage() {
  const toast = useToast();
  const [rows, setRows] = useState<Row[]>([]);
  const [totals, setTotals] = useState<Totals | null>(null);
  const [limit, setLimit] = useState(200);
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
        const d = await api.get<{ totals: Totals; rows: Row[] }>("/ledgers/profit");
        setTotals(d.totals); setRows(d.rows);
      } catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
    })();
  }, [toast]);

  const doExport = useCallback(async (fmt: "pdf" | "xlsx") => {
    setExpOpen(false);
    try { await api.download(`/ledgers/profit/export?fmt=${fmt}`, `profit_ledger.${fmt}`); }
    catch (e) { toast.error(errMsg(e, "Export failed.")); }
  }, [toast]);

  const capped = limit ? rows.slice(-limit) : rows;   // newest N (rows oldest-first)
  const shown = q
    ? capped.filter((r) => [r.txn_date, r.bapari_name, r.factory_name].some((v) => (v || "").toLowerCase().includes(q.toLowerCase())))
    : capped;
  const profit = totals?.profit ?? 0;

  return (
    <div>
      <div className="tiles" style={{ marginBottom: 12 }}>
        <Card label="Total profit" value={money(profit)} color={profit >= 0 ? "#2e7d32" : "#c62828"} icon="trending-up" sub={totals ? `${totals.trades} trades` : undefined} />
        <Card label="Total sales" value={money(totals?.sale ?? 0)} color="#1565c0" icon="receipt" />
        <Card label="Total purchases" value={money(totals?.purchase ?? 0)} color="#6d28d9" icon="cart" />
        <Card label="Avg margin" value={`${g(totals?.margin_pct ?? 0)}%`} color="#00838f" icon="pie-chart" />
      </div>

      <div className="toolbar" style={{ alignItems: "center" }}>
        <span className="tb-lbl">Show:</span>
        <select className="input" style={{ maxWidth: 110 }} value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
          {LIMITS.map((l) => <option key={l.v} value={l.v}>{l.label}</option>)}
        </select>
        <div className="search-wrap" style={{ minWidth: 160 }}><Icon name="search" size={16} /><input className="input" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} /></div>
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

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th style={{ textAlign: "left" }}>Date</th>
            <th style={{ textAlign: "left" }}>Supplier</th>
            <th style={{ textAlign: "left" }}>Factory</th>
            <th className="right">Weight</th>
            <th className="right">Buy rate</th>
            <th className="right">Sell rate</th>
            <th className="right">Profit</th>
            <th className="right">Margin %</th>
          </tr></thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={8} className="empty">No trades.</td></tr>}
            {shown.map((r) => (
              <tr key={r.id}>
                <td>{r.txn_date}</td>
                <td>{r.bapari_name || "—"}</td>
                <td>{r.factory_name || "—"}</td>
                <td className="right">{g(r.weight)}</td>
                <td className="right">{money(r.bapari_rate)}</td>
                <td className="right">{money(r.factory_rate)}</td>
                <td className="right" style={{ color: r.profit >= 0 ? "#2e7d32" : "#c62828" }}>{money(r.profit)}</td>
                <td className="right">{g(rowMargin(r))}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
