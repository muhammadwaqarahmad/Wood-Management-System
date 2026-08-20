"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";

type Cards = {
  sales: number; purchases: number; profit: number; trades: number;
  expBusiness: number; expHouse: number; receivable: number; payable: number;
  loans: number; loansGiven: number; bankTotal: number; cash: number;
  available: number; unclaimed: number;
};
type SeriesPoint = { label: string; sales: number; purchases: number; profit: number; expenses: number };
type TableRow = { key: string; amount: number; sign: number };
type Bank = { name: string; balance: number };
type Summary = { cards: Cards; series: SeriesPoint[]; table: TableRow[]; banks: Bank[] };

const TONES: Record<string, string> = {
  indigo: "#6366f1", sky: "#0ea5e9", emerald: "#10b981",
  amber: "#f59e0b", rose: "#f43f5e", violet: "#8b5cf6", slate: "#64748b",
};
// Chart series colours — the desktop's CVD-validated categorical set (light theme).
const SERIES = { sales: "#2a78d6", purchases: "#008300", profit: "#e87ba4", expenses: "#eda100" };
// Summary-table row labels (desktop _LBL).
const LBL: Record<string, string> = {
  banks: "Bank Accounts", cash: "Cash", receivable: "To receive",
  loans_given: "Loans given", payable: "To give", loans: "Loans taken",
  net_worth: "Net position",
};

const PERIODS: { key: string; label: string }[] = [
  { key: "all", label: "All time" },
  { key: "day", label: "Today" },
  { key: "month", label: "This month" },
  { key: "year", label: "This year" },
  { key: "custom", label: "Custom" },
];
const iso = (d: Date) => d.toISOString().slice(0, 10);
function rangeFor(p: string, from: string, to: string): string {
  const today = new Date();
  if (p === "day") return `?start=${iso(today)}&end=${iso(today)}`;
  if (p === "month") return `?start=${iso(new Date(today.getFullYear(), today.getMonth(), 1))}&end=${iso(today)}`;
  if (p === "year") return `?start=${iso(new Date(today.getFullYear(), 0, 1))}&end=${iso(today)}`;
  if (p === "custom") return `?start=${from}&end=${to}`;
  return "";
}
const amtColor = (v: number) => (v > 0 ? "var(--pos)" : v < 0 ? "var(--neg)" : "var(--muted)");

function Tile({ label, value, tone, icon, signed, count }: {
  label: string; value: number; tone: string; icon: string; signed?: boolean; count?: boolean;
}) {
  const c = TONES[tone];
  const valColor = signed ? (value > 0 ? "var(--pos)" : value < 0 ? "var(--neg)" : "var(--text)") : "var(--text)";
  return (
    <div className="tile" style={{ borderLeftColor: c }}>
      <div className="cap">
        <span className="chip" style={{ background: `linear-gradient(135deg, ${c}, color-mix(in srgb, ${c} 60%, #fff))` }}>
          <Icon name={icon} size={16} />
        </span>
        {label}
      </div>
      <div className="val" style={{ color: valColor }}>
        {count ? value : money(value)}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [period, setPeriod] = useState("day");
  const [from, setFrom] = useState(() => iso(new Date(Date.now() - 30 * 864e5)));
  const [to, setTo] = useState(() => iso(new Date()));
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const [showAllBanks, setShowAllBanks] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try { setData(await api.get<Summary>(`/dashboard${rangeFor(period, from, to)}`)); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't reach the API."); }
  }, [period, from, to]);
  useEffect(() => { load(); }, [load]);

  if (error) return <div className="card notice"><strong>Couldn&apos;t load.</strong><p className="muted">{error}</p></div>;
  if (!data) return <p className="muted">Loading…</p>;
  const c = data.cards;

  return (
    <div>
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

      <div className="section-label">Period Summary</div>
      <div className="tiles" style={{ marginBottom: 18 }}>
        <Tile label="Sale Bill" value={c.sales} tone="indigo" icon="receipt" />
        <Tile label="Purchase Bill" value={c.purchases} tone="sky" icon="cart" />
        <Tile label="Profit" value={c.profit} tone="emerald" icon="trending-up" signed />
        <Tile label="Business Expenses" value={c.expBusiness} tone="amber" icon="trending-down" />
        <Tile label="House Expenses" value={c.expHouse} tone="amber" icon="trending-down" />
        <Tile label="Trades" value={c.trades} tone="slate" icon="database" count />
      </div>

      <div className="section-label">Financial Position</div>
      <div className="tiles" style={{ marginBottom: 18 }}>
        <Tile label="Bank Accounts" value={c.bankTotal} tone="indigo" icon="landmark" />
        <Tile label="Cash" value={c.cash} tone="indigo" icon="wallet" />
        <Tile label="Available" value={c.available} tone="violet" icon="pie-chart" signed />
        <Tile label="Unclaimed Total" value={c.unclaimed} tone="amber" icon="info" />
        <Tile label="To Receive" value={c.receivable} tone="emerald" icon="trending-up" signed />
        <Tile label="To Give" value={c.payable} tone="rose" icon="trending-down" signed />
        <Tile label="Loans Taken" value={c.loans} tone="rose" icon="hand-coins" signed />
        <Tile label="Loans Given" value={c.loansGiven} tone="emerald" icon="hand-coins" signed />
      </div>

      <div className="chart-row">
        <div className="card">
          <div className="card-head"><span className="chip"><Icon name="trending-up" size={15} /></span><span className="h">Sales &amp; Purchases</span></div>
          <BarChart data={data.series} keys={["sales", "purchases"]} colors={[SERIES.sales, SERIES.purchases]} labels={["Sale bill", "Purchase bill"]} />
        </div>
        <div className="card">
          <div className="card-head"><span className="chip"><Icon name="pie-chart" size={15} /></span><span className="h">Profit &amp; Expenses</span></div>
          <BarChart data={data.series} keys={["profit", "expenses"]} colors={[SERIES.profit, SERIES.expenses]} labels={["Profit", "Expenses"]} />
        </div>
      </div>

      {/* Summary (plus/minus) + Bank balances */}
      <div className="dash-tables">
        <div className="card">
          <div className="card-head"><span className="chip"><Icon name="book-text" size={15} /></span><span className="h">Summary</span></div>
          {data.table.map((r) => {
            const disp = r.sign === 0 ? r.amount : r.sign * r.amount;
            const shown = r.sign < 0 ? -r.amount : r.amount;
            const signTxt = r.sign > 0 ? "+" : r.sign < 0 ? "−" : "=";
            return (
              <div key={r.key} className={"kv-row" + (r.sign === 0 ? " total" : "")}>
                <span className="kv-n">{LBL[r.key] ?? r.key}</span>
                <span className="kv-s">{signTxt}</span>
                <span className="kv-a" style={{ color: amtColor(disp) }}>{money(shown)}</span>
              </div>
            );
          })}
        </div>
        <div className="card">
          <div className="card-head"><span className="chip"><Icon name="landmark" size={15} /></span><span className="h">Bank Balances</span></div>
          {data.banks.length === 0 && <p className="muted" style={{ margin: 0 }}>No accounts.</p>}
          {(showAllBanks ? data.banks : data.banks.slice(0, 8)).map((b, i) => (
            <div key={i} className="kv-row">
              <span className="kv-n">{b.name}</span>
              <span className="kv-a" style={{ color: amtColor(b.balance) }}>{money(b.balance)}</span>
            </div>
          ))}
          {data.banks.length > 8 && (
            <button className="link-btn" onClick={() => setShowAllBanks((v) => !v)}>
              {showAllBanks ? "Show less" : `Show all (${data.banks.length})`}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function BarChart({ data, keys, colors, labels }: {
  data: SeriesPoint[]; keys: (keyof SeriesPoint)[]; colors: string[]; labels: string[];
}) {
  const max = Math.max(1, ...data.flatMap((d) => keys.map((k) => Number(d[k]) || 0)));
  if (data.length === 0 || max <= 1) {
    return <div className="chart-empty">No data for this period</div>;
  }
  return (
    <div>
      <div className="chart-legend">
        {labels.map((l, i) => (
          <span key={l}><i style={{ background: colors[i] }} />{l}</span>
        ))}
      </div>
      <div className="chart">
        {data.map((d) => (
          <div className="chart-col" key={d.label}>
            <div className="chart-bars">
              {keys.map((k, i) => (
                <div key={String(k)} className="bar"
                  style={{ height: `${(Number(d[k]) || 0) / max * 100}%`, background: colors[i] }}
                  title={`${labels[i]}: ${money(Number(d[k]) || 0)}`} />
              ))}
            </div>
            <div className="chart-x">{d.label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
