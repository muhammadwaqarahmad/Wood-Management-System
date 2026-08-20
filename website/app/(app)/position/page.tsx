"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop PositionScreen (timber/ui/screens/position_screen.py):
   five always-on headline tiles (Total available / To receive / To give /
   Cheque balance / Net worth), then a Bank / To receive / To give switcher —
   each section with its own summary cards, search and table — plus export. */

type Account = { id: number; name: string; bank_name: string | null; closing: number; is_cash: boolean };
type PartyRow = { name: string; contact: string; kind: string; amount: number };
type Position = {
  bank_total: number; cash_balance: number; cheque_total: number;
  unclaimed_total: number; grand_total: number;
  total_receivable: number; total_payable: number;
  accounts: Account[]; receivables: PartyRow[]; payables: PartyRow[];
};

const KIND_LABEL: Record<string, string> = { supplier: "Supplier", factory: "Factory", loan: "Loan" };
const TABS = [
  { v: "bank", label: "Bank", icon: "landmark" },
  { v: "receivable", label: "To receive", icon: "trending-up" },
  { v: "payable", label: "To give", icon: "trending-down" },
];
const amtColor = (v: number) => (v > 0 ? "var(--pos)" : v < 0 ? "var(--neg)" : "var(--muted)");
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);

function Tile({ label, value, color, icon, valueColor }: {
  label: string; value: number; color: string; icon: string; valueColor?: string;
}) {
  return (
    <div className="tile" style={{ borderLeftColor: color }}>
      <div className="cap">
        <span className="chip" style={{ background: `linear-gradient(135deg, ${color}, color-mix(in srgb, ${color} 60%, #fff))` }}>
          <Icon name={icon} size={16} />
        </span>
        {label}
      </div>
      <div className="val" style={valueColor ? { color: valueColor } : undefined}>{money(value)}</div>
    </div>
  );
}
function CountTile({ label, value, color, icon }: { label: string; value: number; color: string; icon: string }) {
  return (
    <div className="tile" style={{ borderLeftColor: color }}>
      <div className="cap">
        <span className="chip" style={{ background: `linear-gradient(135deg, ${color}, color-mix(in srgb, ${color} 60%, #fff))` }}>
          <Icon name={icon} size={16} />
        </span>
        {label}
      </div>
      <div className="val">{value}</div>
    </div>
  );
}

export default function PositionPage() {
  const toast = useToast();
  const [p, setP] = useState<Position | null>(null);
  const [tab, setTab] = useState("bank");
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
      try { setP(await api.get<Position>("/ledgers/position")); }
      catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
    })();
  }, [toast]);

  async function doExport(fmt: "pdf" | "xlsx") {
    setExpOpen(false);
    try { await api.download(`/ledgers/position/export?fmt=${fmt}&sections=${tab}`, `financial_position.${fmt}`); }
    catch (e) { toast.error(errMsg(e, "Export failed.")); }
  }

  const net = useMemo(() => p ? p.grand_total + p.total_receivable + p.total_payable : 0, [p]);

  if (!p) return <p className="muted">Loading…</p>;

  const rows: PartyRow[] = tab === "receivable" ? p.receivables : tab === "payable" ? p.payables : [];
  const ql = q.toLowerCase();
  const banksShown = tab === "bank" && q
    ? p.accounts.filter((a) => [a.name, a.bank_name].some((v) => (v || "").toLowerCase().includes(ql)))
    : p.accounts;
  const partiesShown = q ? rows.filter((r) => [r.name, r.contact].some((v) => (v || "").toLowerCase().includes(ql))) : rows;

  return (
    <div>
      {/* headline — always visible */}
      <div className="tiles" style={{ marginBottom: 12 }}>
        <Tile label="Total available" value={p.grand_total} color="#6366f1" icon="wallet" />
        <Tile label="To receive" value={p.total_receivable} color="#10b981" icon="trending-up" valueColor="var(--pos)" />
        <Tile label="To give" value={p.total_payable} color="#f43f5e" icon="trending-down" valueColor="var(--neg)" />
        <Tile label="Cheque balance" value={p.cheque_total} color="#f59e0b" icon="file-check" />
        <Tile label="Net worth" value={net} color="#8b5cf6" icon="pie-chart" valueColor={amtColor(net)} />
      </div>

      {/* section switcher + export */}
      <div className="md-tabs" style={{ display: "flex", alignItems: "center" }}>
        {TABS.map((t) => (
          <button key={t.v} className={"md-tab" + (tab === t.v ? " on" : "")} onClick={() => { setTab(t.v); setQ(""); }}>
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

      {/* section cards */}
      <div className="tiles" style={{ margin: "12px 0" }}>
        {tab === "bank" && <>
          <Tile label="Bank" value={p.bank_total} color="#3b82f6" icon="landmark" />
          <Tile label="Cash position" value={p.cash_balance} color="#64748b" icon="wallet" valueColor={amtColor(p.cash_balance)} />
          <Tile label="Cheque balance" value={p.cheque_total} color="#d97706" icon="file-check" />
          {p.unclaimed_total > 0 && <Tile label="Unclaimed total" value={p.unclaimed_total} color="#d97706" icon="info" />}
          <Tile label="Total" value={p.grand_total} color="#64748b" icon="pie-chart" valueColor={amtColor(p.grand_total)} />
        </>}
        {tab === "receivable" && <>
          <Tile label="To receive" value={p.total_receivable} color="#10b981" icon="trending-up" valueColor="var(--pos)" />
          <CountTile label="Parties" value={p.receivables.length} color="#64748b" icon="book-user" />
        </>}
        {tab === "payable" && <>
          <Tile label="To give" value={p.total_payable} color="#f43f5e" icon="trending-down" valueColor="var(--neg)" />
          <CountTile label="Parties" value={p.payables.length} color="#64748b" icon="book-user" />
        </>}
      </div>

      <div className="md-bar">
        <div className="search-wrap"><Icon name="search" size={16} /><input className="input" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>

      <div className="tbl-wrap">
        {tab === "bank" ? (
          <table className="tbl">
            <thead><tr><th style={{ textAlign: "left" }}>Name</th><th style={{ textAlign: "left" }}>Bank name</th><th className="right">Balance</th></tr></thead>
            <tbody>
              {banksShown.length === 0 && <tr><td colSpan={3} className="empty">No accounts.</td></tr>}
              {banksShown.map((a) => (
                <tr key={a.id}>
                  <td>{a.name}</td>
                  <td>{a.bank_name || "—"}</td>
                  <td className="right" style={{ color: amtColor(a.closing) }}>{money(a.closing)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="tbl">
            <thead><tr>
              <th style={{ textAlign: "left" }}>Name</th><th style={{ textAlign: "left" }}>Contact</th>
              <th style={{ textAlign: "left" }}>Type</th><th className="right">Amount</th>
            </tr></thead>
            <tbody>
              {partiesShown.length === 0 && <tr><td colSpan={4} className="empty">Nothing here.</td></tr>}
              {partiesShown.map((r, i) => (
                <tr key={i}>
                  <td>{r.name}</td>
                  <td>{r.contact || "—"}</td>
                  <td>{KIND_LABEL[r.kind] || r.kind}</td>
                  <td className="right" style={{ color: tab === "receivable" ? "var(--pos)" : "var(--neg)" }}>{money(r.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
