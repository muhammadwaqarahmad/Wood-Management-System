"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { money, today } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop TransfersScreen (timber/ui/screens/transfers_screen.py):
   move money between accounts. Two totals tiles, a period-filtered history,
   a "Transfer money" dialog, and Edit / Delete via a Manage menu. */

type Account = { id: number; name: string; is_active: boolean };
type Transfer = { id: number; txn_date: string; from_name: string; to_name: string; amount: number; note: string };

const PERIODS = [
  { v: "day", label: "Day" }, { v: "week", label: "Week" }, { v: "month", label: "Month" },
  { v: "year", label: "Year" }, { v: "all", label: "All" },
];
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function rangeQS(p: string): string {
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
  return "";
}

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
function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="fld"><span>{label}</span>{children}</label>;
}

const blank = () => ({ txn_date: today(), from_account_id: "", to_account_id: "", amount: "", note: "" });

export default function TransfersPage() {
  const toast = useToast();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [rows, setRows] = useState<Transfer[]>([]);
  const [period, setPeriod] = useState("day");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const [dialog, setDialog] = useState<null | "add" | number>(null);
  const [f, setF] = useState(blank());
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [accs, tr] = await Promise.all([
        api.get<Account[]>("/money/accounts"),
        api.get<Transfer[]>(`/money/transfers?_=1${rangeQS(period)}`),
      ]);
      setAccounts(accs.filter((a) => a.is_active));
      setRows(tr);
    } catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
  }, [period, toast]);
  useEffect(() => { load(); }, [load]);

  const current = rows.find((r) => r.id === sel) || null;
  const idByName = (name: string) => accounts.find((a) => a.name === name)?.id ?? "";

  function openAdd() {
    const first = accounts[0]?.id ?? "";
    const second = accounts[1]?.id ?? first;
    setF({ ...blank(), from_account_id: String(first), to_account_id: String(second) });
    setDialog("add");
  }
  function openEdit() {
    if (!current) { toast.warning("Select a transfer first."); return; }
    setF({
      txn_date: current.txn_date, amount: String(current.amount), note: current.note || "",
      from_account_id: String(idByName(current.from_name)), to_account_id: String(idByName(current.to_name)),
    });
    setDialog(current.id);
  }
  async function save() {
    if (!f.from_account_id || !f.to_account_id) { toast.warning("Pick both accounts."); return; }
    if (f.from_account_id === f.to_account_id) { toast.warning("Source and destination must differ."); return; }
    if (!(Number(f.amount) > 0)) { toast.warning("Enter an amount."); return; }
    setBusy(true);
    const payload = {
      txn_date: f.txn_date, from_account_id: Number(f.from_account_id), to_account_id: Number(f.to_account_id),
      amount: Number(f.amount), note: f.note.trim() || null,
    };
    try {
      if (dialog === "add") await api.post("/money/transfers", payload);
      else await api.put(`/money/transfers/${dialog}`, payload);
      setDialog(null); toast.success("Saved."); await load();
    } catch (e) { toast.error(errMsg(e, "Could not save.")); }
    finally { setBusy(false); }
  }
  async function del() {
    if (!current) { toast.warning("Select a transfer first."); return; }
    if (!(await toast.confirm({ title: "Delete transfer", text: `Delete the transfer of ${money(current.amount)} (${current.from_name} → ${current.to_name})?`, danger: true, okText: "Delete" }))) return;
    try { await api.del(`/money/transfers/${current.id}`); setSel(null); toast.success("Deleted."); await load(); }
    catch (e) { toast.error(errMsg(e, "Could not delete.")); }
  }

  const shown = q ? rows.filter((r) => [r.from_name, r.to_name, r.note].some((v) => (v || "").toLowerCase().includes(q.toLowerCase()))) : rows;
  const total = rows.reduce((s, r) => s + r.amount, 0);

  return (
    <div>
      <div className="tiles" style={{ marginBottom: 12 }}>
        <Tile label="Transfers" value={String(rows.length)} color="#6366f1" icon="transfer" />
        <Tile label="Amount" value={money(total)} color="#10b981" icon="wallet" />
      </div>

      <div className="md-bar">
        <span className="tb-lbl">Period:</span>
        <select className="input" style={{ maxWidth: 130 }} value={period} onChange={(e) => setPeriod(e.target.value)}>
          {PERIODS.map((p) => <option key={p.v} value={p.v}>{p.label}</option>)}
        </select>
        <div className="search-wrap"><Icon name="search" size={16} /><input className="input" placeholder="Search transfers" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <div className="grow" />
        <button className="btn" onClick={openAdd}><Icon name="transfer" size={15} /> Transfer money</button>
        <ManageMenu actions={[
          { label: "Edit", icon: "pencil", run: openEdit },
          "sep",
          { label: "Delete", icon: "trash", run: del, danger: true },
        ]} />
      </div>

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th>Date</th><th style={{ textAlign: "left" }}>From account</th><th style={{ textAlign: "left" }}>To account</th>
            <th className="right">Amount</th><th style={{ textAlign: "left" }}>Notes</th>
          </tr></thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={5} className="empty">No transfers.</td></tr>}
            {shown.map((r) => (
              <tr key={r.id} onClick={() => setSel(r.id)} style={{ cursor: "pointer", ...(sel === r.id ? { background: "var(--sel-row)" } : {}) }}>
                <td>{r.txn_date}</td>
                <td>{r.from_name}</td>
                <td>{r.to_name}</td>
                <td className="right">{money(r.amount)}</td>
                <td>{r.note || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {dialog !== null && (
        <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setDialog(null); }}>
          <div className="modal">
            <div className="dlg-head"><span className="dlg-chip"><Icon name="transfer" size={21} /></span><span className="dlg-title">{dialog === "add" ? "Transfer money" : "Edit transfer"}</span></div>
            <div className="modal-body">
              <Field label="Date"><input className="input" type="date" value={f.txn_date} onChange={(e) => setF({ ...f, txn_date: e.target.value })} /></Field>
              <Field label="From account">
                <select className="input" value={f.from_account_id} onChange={(e) => setF({ ...f, from_account_id: e.target.value })}>
                  <option value="">—</option>
                  {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </Field>
              <Field label="To account">
                <select className="input" value={f.to_account_id} onChange={(e) => setF({ ...f, to_account_id: e.target.value })}>
                  <option value="">—</option>
                  {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </Field>
              <Field label="Amount"><input className="input right" inputMode="decimal" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
              <Field label="Notes"><input className="input" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} /></Field>
            </div>
            <div className="modal-foot">
              <button className="btn-ghost" onClick={() => setDialog(null)}>Cancel</button>
              <button className="btn" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
