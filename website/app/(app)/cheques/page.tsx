"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop ChequeScreen (timber/ui/screens/cheque_screen.py):
   cheques created on the Payment page (method = Cheque) — clear or bounce them
   here. A pending cheque settles the party now but only moves the bank balance
   when it CLEARS; bounce reverses it. Four tiles, a status filter, a table. */

type Cheque = {
  id: number; txn_date: string; party_name: string; direction: string;
  amount: number; account_name: string; reference: string; status: string; cleared_date: string | null;
};

const STATUSES = [
  { v: "", label: "All" }, { v: "pending", label: "Pending" },
  { v: "cleared", label: "Cleared" }, { v: "bounced", label: "Bounced" },
];
const STATUS_LABEL: Record<string, string> = { pending: "Pending", cleared: "Cleared", bounced: "Bounced" };
const STATUS_COLOR: Record<string, string> = { pending: "#b45309", cleared: "#16a34a", bounced: "#c62828" };
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);

function Tile({ label, value, color, icon }: { label: string; value: string; color: string; icon: string }) {
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
function ManageMenu({ actions }: { actions: ({ label: string; icon: string; run: () => void; danger?: boolean } | "sep")[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onDoc(e: MouseEvent) { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  return (
    <div className="manage" ref={ref}>
      <button className="manage-btn" onClick={() => setOpen((o) => !o)}><Icon name="settings" size={15} /> Manage ▾</button>
      {open && (
        <div className="manage-menu">
          {actions.map((a, i) => a === "sep"
            ? <div className="manage-sep" key={"s" + i} />
            : <button key={a.label} className={"manage-item" + (a.danger ? " danger" : "")} onClick={() => { setOpen(false); a.run(); }}><Icon name={a.icon} size={16} /> {a.label}</button>)}
        </div>
      )}
    </div>
  );
}

export default function ChequesPage() {
  const toast = useToast();
  const [status, setStatus] = useState("pending");
  const [rows, setRows] = useState<Cheque[]>([]);
  const [balance, setBalance] = useState(0);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const [chs, sum] = await Promise.all([
        api.get<Cheque[]>(`/money/cheques${status ? `?status=${status}` : ""}`),
        api.get<{ cheque_balance: number }>("/money/summary"),
      ]);
      setRows(chs); setBalance(sum.cheque_balance);
    } catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
  }, [status, toast]);
  useEffect(() => { load(); }, [load]);

  // Counts follow the loaded (status-filtered) rows, like the desktop.
  const counts = rows.reduce((a, r) => { a[r.status] = (a[r.status] || 0) + 1; return a; }, {} as Record<string, number>);
  const current = rows.find((r) => r.id === sel) || null;

  function requirePending(): Cheque | null {
    if (!current) { toast.warning("Select a cheque first."); return null; }
    if (current.status !== "pending") { toast.warning("Only pending cheques can be cleared or bounced."); return null; }
    return current;
  }
  async function clear() {
    const c = requirePending(); if (!c) return;
    try { await api.post(`/money/cheques/${c.id}/clear`); toast.success("Cheque cleared."); await load(); }
    catch (e) { toast.error(errMsg(e, "Failed.")); }
  }
  async function bounce() {
    const c = requirePending(); if (!c) return;
    if (!(await toast.confirm({ title: "Bounce cheque", text: `Bounce the cheque of ${money(c.amount)} (${c.party_name})? This reverses it.`, danger: true, okText: "Bounce" }))) return;
    try { await api.post(`/money/cheques/${c.id}/bounce`); toast.success("Cheque bounced."); await load(); }
    catch (e) { toast.error(errMsg(e, "Failed.")); }
  }

  const shown = q ? rows.filter((r) => [r.party_name, r.reference, r.account_name].some((v) => (v || "").toLowerCase().includes(q.toLowerCase()))) : rows;

  return (
    <div>
      <div className="tiles" style={{ marginBottom: 12 }}>
        <Tile label="Cheque balance" value={money(balance)} color="#f59e0b" icon="file-check" />
        <Tile label="Pending" value={String(counts.pending || 0)} color="#0ea5e9" icon="alarm-clock" />
        <Tile label="Cleared" value={String(counts.cleared || 0)} color="#10b981" icon="check" />
        <Tile label="Bounced" value={String(counts.bounced || 0)} color="#f43f5e" icon="alert-triangle" />
      </div>

      <div className="md-bar">
        <div className="search-wrap"><Icon name="search" size={16} /><input className="input" placeholder="Search cheques" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <div className="grow" />
        <span className="tb-lbl">Status:</span>
        <select className="input" style={{ maxWidth: 140 }} value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUSES.map((s) => <option key={s.v} value={s.v}>{s.label}</option>)}
        </select>
      </div>

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th>Date</th><th style={{ textAlign: "left" }}>Party</th><th>Direction</th>
            <th className="right">Amount</th><th style={{ textAlign: "left" }}>Bank account</th>
            <th style={{ textAlign: "left" }}>Reference</th><th>Status</th><th>Cleared on</th>
          </tr></thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={8} className="empty">No cheques.</td></tr>}
            {shown.map((r) => (
              <tr key={r.id} onClick={() => setSel(r.id)} style={{ cursor: "pointer", ...(sel === r.id ? { background: "var(--sel-row)" } : {}) }}>
                <td>{r.txn_date}</td>
                <td>{r.party_name}</td>
                <td>{r.direction === "in" ? "Received (in)" : "Issued (out)"}</td>
                <td className="right">{money(r.amount)}</td>
                <td>{r.account_name}</td>
                <td>{r.reference || "—"}</td>
                <td style={{ color: STATUS_COLOR[r.status] || "#475569", fontWeight: 600 }}>{STATUS_LABEL[r.status] || r.status}</td>
                <td style={{ textAlign: "center" }}>{r.cleared_date || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="md-toolbar bottom">
        <ManageMenu actions={[
          { label: "Clear", icon: "check", run: clear },
          "sep",
          { label: "Bounce", icon: "x", run: bounce, danger: true },
        ]} />
        <div className="grow" />
      </div>
    </div>
  );
}
