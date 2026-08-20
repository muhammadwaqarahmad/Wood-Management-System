"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop ReportsScreen (timber/ui/screens/reports_screen.py):
   Cash Flow / Factories / Suppliers tabs, a period filter, and Export. Cash flow
   shows the worth hero + section cards; the party tabs show tiles + a table. */

const TONES: Record<string, string> = {
  indigo: "#6366f1", sky: "#0ea5e9", emerald: "#10b981", amber: "#f59e0b", rose: "#f43f5e", slate: "#64748b",
};
const TABS = [
  { key: "cashflow", label: "Cash flow", icon: "wallet" },
  { key: "factory", label: "Factories", icon: "factory" },
  { key: "supplier", label: "Suppliers", icon: "book-user" },
];
const PERIODS = [
  { key: "all", label: "All time" }, { key: "day", label: "Today" },
  { key: "month", label: "This month" }, { key: "year", label: "This year" },
  { key: "custom", label: "Custom" },
];
const CF_SECTIONS: Record<string, string> = {
  position: "1. Cash & banks", balances: "2. To receive / to give",
  cheques: "3. In cheque form", unclaimed: "Unknown Total Amount", flows: "4. This period",
};
const CF_LABELS: Record<string, string> = {
  banks: "Bank accounts", cash: "Cash", available: "Total available",
  cheques_in: "Cheques in hand (pending)", unclaimed: "Unclaimed",
  receivable: "To receive", loans_given: "Loans given", payable: "To give",
  loans: "Loans taken", profit: "Total profit", exp_business: "Business expenses",
  exp_house: "House expenses", profit_after: "Profit after expenses",
};

const iso = (d: Date) => d.toISOString().slice(0, 10);
function range(p: string, from: string, to: string): string {
  const t = new Date();
  if (p === "day") return `&start=${iso(t)}&end=${iso(t)}`;
  if (p === "month") return `&start=${iso(new Date(t.getFullYear(), t.getMonth(), 1))}&end=${iso(t)}`;
  if (p === "year") return `&start=${iso(new Date(t.getFullYear(), 0, 1))}&end=${iso(t)}`;
  if (p === "custom") return `&start=${from}&end=${to}`;
  return "";
}
const amtColor = (v: number) => (v > 0 ? "var(--pos)" : v < 0 ? "var(--neg)" : "var(--muted)");

type CashRow = { section: string; key: string; amount: number; sign: number };
type CashData = { worth: number; rows: CashRow[] };
type PartyOverall = { trades: number; volume: number; profit: number; receivable: number; payable: number; over30: number; over60: number };
type PartyRow = { name: string; trades: number; volume: number; balance: number; over30: number; over60: number };
type PartyData = { overall: PartyOverall; rows: PartyRow[] };

export default function ReportsPage() {
  const toast = useToast();
  const [tab, setTab] = useState("cashflow");
  const [period, setPeriod] = useState("day");
  const [from, setFrom] = useState(() => iso(new Date(Date.now() - 30 * 864e5)));
  const [to, setTo] = useState(() => iso(new Date()));
  const [cash, setCash] = useState<CashData | null>(null);
  const [party, setParty] = useState<PartyData | null>(null);
  const [error, setError] = useState("");
  const [expOpen, setExpOpen] = useState(false);
  const expRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onDoc(e: MouseEvent) { if (expRef.current && !expRef.current.contains(e.target as Node)) setExpOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  async function doExport(fmt: "pdf" | "xlsx") {
    setExpOpen(false);
    try { await api.download(`/reports/export?fmt=${fmt}&sections=${tab}${range(period, from, to)}`, `reports.${fmt}`); }
    catch (e) { toast.error(e instanceof ApiError ? e.message : "Export failed."); }
  }

  const load = useCallback(async () => {
    setError("");
    const q = range(period, from, to);
    try {
      if (tab === "cashflow") setCash(await api.get<CashData>(`/reports/cashflow?_=1${q}`));
      else setParty(await api.get<PartyData>(`/reports/parties?kind=${tab}${q}`));
    } catch (e) { setError(e instanceof ApiError ? e.message : "Couldn't reach the API."); }
  }, [tab, period, from, to]);
  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <div className="md-tabs" style={{ display: "flex", alignItems: "center" }}>
        {TABS.map((t) => (
          <button key={t.key} className={"md-tab" + (tab === t.key ? " on" : "")} onClick={() => setTab(t.key)}>
            <Icon name={t.icon} size={16} /> {t.label}
          </button>
        ))}
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

      <div className="toolbar">
        <span style={{ fontWeight: 700, color: "var(--muted)" }}>Period:</span>
        <select className="input" style={{ maxWidth: 180 }} value={period} onChange={(e) => setPeriod(e.target.value)}>
          {PERIODS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
        </select>
        {period === "custom" && (
          <>
            <input className="input" type="date" style={{ maxWidth: 170 }} value={from} onChange={(e) => setFrom(e.target.value)} />
            <input className="input" type="date" style={{ maxWidth: 170 }} value={to} onChange={(e) => setTo(e.target.value)} />
          </>
        )}
      </div>

      {error && <div className="card notice"><strong>Couldn&apos;t load.</strong><p className="set-note">{error}</p></div>}
      {!error && tab === "cashflow" && <CashFlow data={cash} />}
      {!error && tab !== "cashflow" && <Parties data={party} isFactory={tab === "factory"} />}
    </div>
  );
}

function CashFlow({ data }: { data: CashData | null }) {
  if (!data) return <p className="muted">Loading…</p>;
  const sections: { sec: string; rows: CashRow[] }[] = [];
  for (const r of data.rows) {
    if (r.section === "worth") continue;
    const last = sections[sections.length - 1];
    if (last && last.sec === r.section) last.rows.push(r);
    else sections.push({ sec: r.section, rows: [r] });
  }
  return (
    <div>
      <div className="cf-hero">
        <div className="cap">Total business worth</div>
        <div className="worth" style={{ color: data.worth < 0 ? "#fecaca" : "#fff" }}>{money(data.worth)}</div>
      </div>
      <div className="cf-grid">
        {sections.map(({ sec, rows }) => (
          <div className="card" key={sec}>
            <div className="card-head"><span className="chip"><Icon name="wallet" size={15} /></span><span className="h">{CF_SECTIONS[sec] ?? sec}</span></div>
            {rows.map((r) => {
              const disp = r.sign === 0 ? r.amount : r.sign * r.amount;
              return (
                <div key={r.key} className={"kv-row" + (r.sign === 0 ? " total" : "")}>
                  <span className="kv-n">{CF_LABELS[r.key] ?? r.key}</span>
                  <span className="kv-s">{r.sign > 0 ? "+" : r.sign < 0 ? "−" : "="}</span>
                  <span className="kv-a" style={{ color: amtColor(disp) }}>{money(r.sign < 0 ? -r.amount : r.amount)}</span>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function Tile({ label, value, tone, icon, signed, count }: {
  label: string; value: number; tone: string; icon: string; signed?: boolean; count?: boolean;
}) {
  const c = TONES[tone];
  return (
    <div className="tile" style={{ borderLeftColor: c }}>
      <div className="cap">
        <span className="chip" style={{ background: `linear-gradient(135deg, ${c}, color-mix(in srgb, ${c} 60%, #fff))` }}>
          <Icon name={icon} size={16} />
        </span>{label}
      </div>
      <div className="val" style={{ color: signed ? amtColor(value) : "var(--text)" }}>{count ? value : money(value)}</div>
    </div>
  );
}

function Parties({ data, isFactory }: { data: PartyData | null; isFactory: boolean }) {
  if (!data) return <p className="muted">Loading…</p>;
  const o = data.overall;
  const volLabel = isFactory ? "Total sales" : "Total purchases";
  return (
    <div>
      <div className="tiles" style={{ marginBottom: 16 }}>
        <Tile label="Trades" value={o.trades} tone="slate" icon="database" count />
        <Tile label={volLabel} value={o.volume} tone={isFactory ? "indigo" : "sky"} icon={isFactory ? "receipt" : "cart"} />
        <Tile label="Profit" value={o.profit} tone="emerald" icon="trending-up" signed />
        <Tile label="To receive" value={o.receivable} tone="emerald" icon="trending-up" signed />
        <Tile label="To give" value={-o.payable} tone="rose" icon="trending-down" signed />
        {isFactory && <Tile label="Overdue 30+ days" value={o.over30} tone="amber" icon="alarm-clock" />}
        {isFactory && <Tile label="Overdue 60+ days" value={o.over60} tone="rose" icon="alarm-clock" />}
      </div>
      <div className="card">
        <div className="card-head">
          <span className="chip"><Icon name={isFactory ? "factory" : "book-user"} size={15} /></span>
          <span className="h">{isFactory ? "Factories" : "Suppliers"}</span>
        </div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr>
              <th style={{ textAlign: "left" }}>Name</th><th>Trades</th><th>{volLabel}</th>
              <th>To receive</th><th>To give</th>
              {isFactory && <><th>Overdue 30+</th><th>Overdue 60+</th></>}
            </tr></thead>
            <tbody>
              {data.rows.length === 0 && <tr><td colSpan={isFactory ? 7 : 5} className="empty">No data for this period.</td></tr>}
              {data.rows.map((r, i) => (
                <tr key={i}>
                  <td>{r.name}</td>
                  <td className="right">{r.trades}</td>
                  <td className="right">{money(r.volume)}</td>
                  <td className="right" style={{ color: r.balance > 0 ? "var(--pos)" : "var(--muted)" }}>{r.balance > 0 ? money(r.balance) : "—"}</td>
                  <td className="right" style={{ color: r.balance < 0 ? "var(--neg)" : "var(--muted)" }}>{r.balance < 0 ? money(-r.balance) : "—"}</td>
                  {isFactory && <td className="right" style={{ color: r.over30 ? "#d97706" : "var(--muted)" }}>{r.over30 ? money(r.over30) : "—"}</td>}
                  {isFactory && <td className="right" style={{ color: r.over60 ? "var(--neg)" : "var(--muted)" }}>{r.over60 ? money(r.over60) : "—"}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
