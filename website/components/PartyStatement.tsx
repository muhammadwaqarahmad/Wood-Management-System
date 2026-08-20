"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { SearchSelect } from "@/components/SearchSelect";
import { useToast } from "@/lib/toast";

/* Shared per-party statement — the desktop's PartyStatementScreen
   (timber/ui/screens/party_statement_screen.py), used by both the Supplier
   Ledger (kind="supplier") and the Factory Ledger (kind="factory"), exactly
   as the desktop subclasses one screen for both. Pick a party + period, see a
   rich running statement (loads with vehicle/wood/weight/rate/freight/bill,
   payments with their route), three summary cards, and PDF/Excel export. */

type Party = { id: number; name: string };
type Entry = {
  entry_date: string; kind: string; counterparty: string; vehicle: string;
  wood: string; weight_text: string; rate: number; freight: number; total: number;
  debit: number; credit: number; expenses: string; payment_detail: string; balance: number;
};
type Statement = {
  party: { id: number; name: string; type: string };
  opening: number; closing: number; total_loads: number; total_paid: number;
  entries: Entry[];
};

const PERIODS = [
  { v: "all", label: "All" }, { v: "day", label: "Day" }, { v: "week", label: "Week" },
  { v: "month", label: "Month" }, { v: "year", label: "Year" }, { v: "custom", label: "Custom range" },
];
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

function Card({ label, value, color, icon }: { label: string; value: string; color: string; icon: string }) {
  return (
    <div className="tile" style={{ borderLeftColor: color }}>
      <div className="cap">
        <span className="chip" style={{ background: `linear-gradient(135deg, ${color}, color-mix(in srgb, ${color} 60%, #fff))` }}>
          <Icon name={icon} size={16} />
        </span>
        {label}
      </div>
      <div className="val" style={{ color }}>{value}</div>
    </div>
  );
}

export function PartyStatement({ kind }: { kind: "supplier" | "factory" }) {
  const toast = useToast();
  const isSupplier = kind === "supplier";
  // The counterparty on a supplier's loads is the factory, and vice-versa.
  const counterLabel = isSupplier ? "Factory" : "Supplier";
  const partyLabel = isSupplier ? "Supplier" : "Factory";
  const loadsCard = isSupplier
    ? { label: "Purchases", icon: "cart" }
    : { label: "Sales", icon: "receipt" };

  const [parties, setParties] = useState<Party[]>([]);
  const [partyId, setPartyId] = useState("");
  const [period, setPeriod] = useState("day");
  const [from, setFrom] = useState(() => iso(new Date()));
  const [to, setTo] = useState(() => iso(new Date()));
  const [st, setSt] = useState<Statement | null>(null);
  const [q, setQ] = useState("");
  const [expOpen, setExpOpen] = useState(false);
  const expRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) { if (expRef.current && !expRef.current.contains(e.target as Node)) setExpOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  useEffect(() => {
    setPartyId(""); setSt(null); setQ("");
    (async () => {
      try { setParties(await api.get<Party[]>(`/parties?kind=${kind}`)); }
      catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
    })();
  }, [kind, toast]);

  const load = useCallback(async () => {
    if (!partyId) { setSt(null); return; }
    try { setSt(await api.get<Statement>(`/parties/${partyId}/statement?_=1${rangeQS(period, from, to)}`)); }
    catch (e) { toast.error(errMsg(e, "Couldn't load the ledger.")); }
  }, [partyId, period, from, to, toast]);
  useEffect(() => { load(); }, [load]);

  async function doExport(fmt: "pdf" | "xlsx") {
    setExpOpen(false);
    if (!partyId) { toast.warning(`Choose a ${kind} first.`); return; }
    try { await api.download(`/parties/${partyId}/statement/export?fmt=${fmt}${rangeQS(period, from, to)}`, `statement.${fmt}`); }
    catch (e) { toast.error(errMsg(e, "Export failed.")); }
  }

  const balCard = useMemo(() => {
    const b = st?.closing ?? 0;
    if (b < 0) return { label: "You owe", value: money(-b), color: "#c62828", icon: "trending-down" };
    if (b > 0) return { label: "Owes you", value: money(b), color: "#16a34a", icon: "trending-up" };
    return { label: "Balance", value: money(0), color: "#64748b", icon: "wallet" };
  }, [st]);

  const rows = st?.entries ?? [];
  const shown = q
    ? rows.filter((e) => [e.entry_date, e.counterparty, e.vehicle, e.wood, e.expenses, e.payment_detail]
        .some((v) => (v || "").toLowerCase().includes(q.toLowerCase())))
    : rows;
  const showCounter = rows.some((e) => e.counterparty);
  const partyOpts = parties.map((p) => ({ value: String(p.id), label: p.name }));

  return (
    <div>
      <div className="toolbar" style={{ alignItems: "center" }}>
        <span className="tb-lbl">{partyLabel}:</span>
        <div style={{ minWidth: 240 }}><SearchSelect value={partyId} options={partyOpts} onChange={(v) => { setPartyId(v); setQ(""); }} placeholder={`Search ${kind}…`} /></div>
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

      {!partyId ? (
        <div className="tbl-wrap"><table className="tbl"><tbody><tr><td className="empty">Choose a {kind} to see their ledger.</td></tr></tbody></table></div>
      ) : !st ? (
        <p className="muted">Loading…</p>
      ) : (
        <>
          <div className="tiles" style={{ margin: "0 0 12px" }}>
            <Card {...balCard} />
            <Card label={loadsCard.label} value={money(st.total_loads)} color="#1565c0" icon={loadsCard.icon} />
            <Card label="Total paid" value={money(st.total_paid)} color="#2e7d32" icon="hand-coins" />
          </div>

          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr>
                <th style={{ textAlign: "left" }}>Date</th>
                <th style={{ textAlign: "left" }}>Description</th>
                {showCounter && <th style={{ textAlign: "left" }}>{counterLabel}</th>}
                <th style={{ textAlign: "left" }}>Vehicle no.</th>
                <th style={{ textAlign: "left" }}>Wood type</th>
                <th className="right">Weight</th>
                <th className="right">Rate</th>
                <th className="right">Freight</th>
                <th className="right">Total</th>
                <th className="right">Bill amount</th>
                <th className="right">Payment</th>
                <th style={{ textAlign: "left" }}>Expenses</th>
                <th className="right">Balance</th>
              </tr></thead>
              <tbody>
                {shown.length === 0 && <tr><td colSpan={showCounter ? 13 : 12} className="empty">No entries in this period.</td></tr>}
                {shown.map((e, i) => {
                  const isLoad = e.kind === "load";
                  const detail = isLoad ? e.expenses : e.payment_detail;
                  return (
                    <tr key={i}>
                      <td>{e.entry_date}</td>
                      <td>{isLoad ? "Load" : "Payment"}</td>
                      {showCounter && <td>{e.counterparty || "—"}</td>}
                      <td>{e.vehicle || "—"}</td>
                      <td>{e.wood || "—"}</td>
                      <td className="right">{e.weight_text || ""}</td>
                      <td className="right">{isLoad ? money(e.rate) : ""}</td>
                      <td className="right">{isLoad && e.freight ? money(-e.freight) : ""}</td>
                      <td className="right">{isLoad ? money(e.total) : ""}</td>
                      <td className="right" style={{ color: e.debit ? "#c62828" : undefined }}>{e.debit ? money(e.debit) : ""}</td>
                      <td className="right" style={{ color: e.credit ? "#2e7d32" : undefined }}>{e.credit ? money(e.credit) : ""}</td>
                      <td style={{ whiteSpace: "normal", maxWidth: 220 }}>{detail || "—"}</td>
                      <td className="right" style={{ color: e.balance < 0 ? "#c62828" : "#2e7d32" }}>{money(e.balance)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
