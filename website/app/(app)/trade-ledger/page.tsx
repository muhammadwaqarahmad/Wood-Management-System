"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop TradeLedgerScreen (timber/ui/screens/trade_ledger_screen.py):
   every trade line — supplier side (buy rate / purchase / paid?) and factory side
   (sell rate / sale / paid?) with vehicle, weight, profit and freight. Period +
   show-limit filters, three totals cards, and PDF/Excel export. */

type Row = {
  txn_date: string; vehicle: string; wood: string; weight_text: string;
  supplier_name: string; buy_rate: number; purchase_bill: number; supplier_status: string;
  factory_name: string; sell_rate: number; sale_bill: number; factory_status: string;
  profit: number;
  loading: number; loading_payer: string; loading_payer2: string | null; loading_split: number;
  freight: number; freight_payer: string; freight_payer2: string | null; freight_split: number;
  unloading: number; unloading_payer: string; unloading_payer2: string | null; unloading_split: number;
};
type Data = { totals: { purchase: number; sale: number; profit: number }; rows: Row[] };

const APP_NAME = "Abdul Sattar Woods";
const PERIODS = [
  { v: "all", label: "All" }, { v: "day", label: "Day" }, { v: "week", label: "Week" },
  { v: "month", label: "Month" }, { v: "year", label: "Year" }, { v: "custom", label: "Custom range" },
];
const LIMITS = [{ v: 200, label: "200" }, { v: 500, label: "500" }, { v: 1000, label: "1000" }, { v: 0, label: "All" }];
const STATUS_LABEL: Record<string, string> = { paid: "Paid", partial: "Partial", unpaid: "Unpaid" };
const STATUS_COLOR: Record<string, string> = { paid: "#16a34a", partial: "#b45309", unpaid: "#c62828" };
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function rangeQS(p: string, from: string, to: string): string {
  const t = new Date(); const Y = t.getFullYear(); const M = t.getMonth();
  if (p === "day") return `&start=${iso(t)}&end=${iso(t)}`;
  if (p === "week") {
    const dow = (t.getDay() + 6) % 7;
    const s = new Date(Y, M, t.getDate() - dow);
    const e = new Date(s); e.setDate(s.getDate() + 6);
    return `&start=${iso(s)}&end=${iso(e)}`;
  }
  if (p === "month") return `&start=${iso(new Date(Y, M, 1))}&end=${iso(new Date(Y, M + 1, 0))}`;
  if (p === "year") return `&start=${iso(new Date(Y, 0, 1))}&end=${iso(new Date(Y, 11, 31))}`;
  if (p === "custom") return `&start=${from}&end=${to}`;
  return "";
}

// Who paid a charge: us -> business, bapari -> supplier, factory -> factory.
function payerLabel(code: string, sup: string, fac: string): string {
  if (code === "us") return APP_NAME;
  if (code === "bapari") return sup || "Supplier";
  if (code === "factory") return fac || "Factory";
  return code || "";
}
function expenseText(amt: number, payer: string, sup: string, fac: string, payer2: string | null, split: number): string {
  if (!(amt > 0)) return "";
  const n1 = payerLabel(payer, sup, fac);
  if (payer2 && split > 0 && split < amt) {
    const n2 = payerLabel(payer2, sup, fac);
    return `${money(amt)} (${money(split)} ${n1}, ${money(amt - split)} ${n2})`;
  }
  return `${money(amt)} (${n1})`;
}
function expensesSummary(r: Row): string {
  const parts: string[] = [];
  const items: [number, string, string | null, number, string][] = [
    [r.freight, r.freight_payer, r.freight_payer2, r.freight_split, "Freight"],
    [r.loading, r.loading_payer, r.loading_payer2, r.loading_split, "Loading"],
    [r.unloading, r.unloading_payer, r.unloading_payer2, r.unloading_split, "Unloading"],
  ];
  for (const [amt, p1, p2, split, key] of items) {
    const t = expenseText(amt, p1, r.supplier_name, r.factory_name, p2, split);
    if (t) parts.push(`${key}: ${t}`);
  }
  return parts.join("\n");
}

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

export default function TradeLedgerPage() {
  const toast = useToast();
  const [period, setPeriod] = useState("day");
  const [from, setFrom] = useState(() => iso(new Date()));
  const [to, setTo] = useState(() => iso(new Date()));
  const [limit, setLimit] = useState(200);
  const [data, setData] = useState<Data | null>(null);
  const [q, setQ] = useState("");
  const [expOpen, setExpOpen] = useState(false);
  const expRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) { if (expRef.current && !expRef.current.contains(e.target as Node)) setExpOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const load = useCallback(async () => {
    try { setData(await api.get<Data>(`/ledgers/trades?_=1${rangeQS(period, from, to)}`)); }
    catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
  }, [period, from, to, toast]);
  useEffect(() => { load(); }, [load]);

  async function doExport(fmt: "pdf" | "xlsx") {
    setExpOpen(false);
    try { await api.download(`/ledgers/trades/export?fmt=${fmt}${rangeQS(period, from, to)}`, `trade_ledger.${fmt}`); }
    catch (e) { toast.error(errMsg(e, "Export failed.")); }
  }

  const rows = data?.rows ?? [];
  // Newest N (rows are oldest-first), then search — matches the desktop.
  const capped = limit ? rows.slice(-limit) : rows;
  const shown = q
    ? capped.filter((r) => [r.txn_date, r.vehicle, r.wood, r.supplier_name, r.factory_name]
        .some((v) => (v || "").toLowerCase().includes(q.toLowerCase())))
    : capped;
  const showFreight = useMemo(() => rows.some((r) => expensesSummary(r) !== ""), [rows]);
  const profit = data?.totals.profit ?? 0;

  return (
    <div>
      <div className="toolbar" style={{ alignItems: "center" }}>
        <span className="tb-lbl">Period:</span>
        <select className="input" style={{ maxWidth: 150 }} value={period} onChange={(e) => setPeriod(e.target.value)}>
          {PERIODS.map((p) => <option key={p.v} value={p.v}>{p.label}</option>)}
        </select>
        {period === "custom" && (
          <>
            <input className="input" type="date" style={{ maxWidth: 160 }} value={from} onChange={(e) => setFrom(e.target.value)} />
            <input className="input" type="date" style={{ maxWidth: 160 }} value={to} onChange={(e) => setTo(e.target.value)} />
          </>
        )}
        <span className="tb-lbl">Show:</span>
        <select className="input" style={{ maxWidth: 110 }} value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
          {LIMITS.map((l) => <option key={l.v} value={l.v}>{l.label}</option>)}
        </select>
        <div className="search-wrap" style={{ minWidth: 160 }}><Icon name="search" size={16} /><input className="input" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} /></div>
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

      <div className="tiles" style={{ margin: "0 0 12px" }}>
        <Card label="Total purchases" value={money(data?.totals.purchase ?? 0)} color="#6d28d9" icon="cart" sub={`${rows.length} trades`} />
        <Card label="Total sales" value={money(data?.totals.sale ?? 0)} color="#1565c0" icon="receipt" />
        <Card label="Total profit" value={money(profit)} color={profit >= 0 ? "#2e7d32" : "#c62828"} icon="trending-up" />
      </div>

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th style={{ textAlign: "left" }}>Date</th>
            <th style={{ textAlign: "left" }}>Vehicle no.</th>
            <th style={{ textAlign: "left" }}>Wood type</th>
            <th className="right">Weight</th>
            <th style={{ textAlign: "left" }}>Supplier</th>
            <th className="right">Buy rate</th>
            <th className="right">Purchase bill</th>
            <th>Status</th>
            <th style={{ textAlign: "left" }}>Factory</th>
            <th className="right">Sell rate</th>
            <th className="right">Sale bill</th>
            <th>Status</th>
            <th className="right">Profit</th>
            {showFreight && <th style={{ textAlign: "left" }}>Freight</th>}
          </tr></thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={showFreight ? 14 : 13} className="empty">No trades in this period.</td></tr>}
            {shown.map((r, i) => (
              <tr key={i}>
                <td>{r.txn_date}</td>
                <td>{r.vehicle || "—"}</td>
                <td>{r.wood || "—"}</td>
                <td className="right">{r.weight_text}</td>
                <td>{r.supplier_name || "—"}</td>
                <td className="right">{money(r.buy_rate)}</td>
                <td className="right">{money(r.purchase_bill)}</td>
                <td style={{ color: STATUS_COLOR[r.supplier_status] || "#475569", fontWeight: 600 }}>{STATUS_LABEL[r.supplier_status] || r.supplier_status}</td>
                <td>{r.factory_name || "—"}</td>
                <td className="right">{money(r.sell_rate)}</td>
                <td className="right">{money(r.sale_bill)}</td>
                <td style={{ color: STATUS_COLOR[r.factory_status] || "#475569", fontWeight: 600 }}>{STATUS_LABEL[r.factory_status] || r.factory_status}</td>
                <td className="right" style={{ color: r.profit >= 0 ? "#2e7d32" : "#c62828" }}>{money(r.profit)}</td>
                {showFreight && <td style={{ whiteSpace: "pre-line", maxWidth: 220 }}>{expensesSummary(r) || "—"}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
