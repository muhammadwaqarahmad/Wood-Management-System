"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { money, today } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop LoansScreen (timber/ui/screens/loans_screen.py):
   money borrowed (taken) or lent (given). Borrowing adds cash to an account,
   repaying takes it out; outstanding = principal - repayments. Two tiles, a
   table, and Add / Repay / Delete via a Manage menu. */

type Account = { id: number; name: string; is_active: boolean };
type Loan = {
  id: number; txn_date: string; lender_name: string; principal: number; repaid: number;
  outstanding: number; account_name: string; expected_return_date: string | null; direction: string;
};

const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const plus3mo = () => { const d = new Date(); d.setMonth(d.getMonth() + 3); return iso(d); };

function Tile({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="tile" style={{ borderLeftColor: color }}>
      <div className="cap">
        <span className="chip" style={{ background: `linear-gradient(135deg, ${color}, color-mix(in srgb, ${color} 60%, #fff))` }}>
          <Icon name="hand-coins" size={16} />
        </span>
        {label}
      </div>
      <div className="val" style={{ color }}>{value}</div>
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

export default function LoansPage() {
  const toast = useToast();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [rows, setRows] = useState<Loan[]>([]);
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [af, setAf] = useState({ direction: "taken", txn_date: today(), lender_name: "", amount: "", bank_account_id: "", expected_return_date: plus3mo(), notes: "" });
  const [repayLoan, setRepayLoan] = useState<Loan | null>(null);
  const [rf, setRf] = useState({ txn_date: today(), amount: "", bank_account_id: "", notes: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [accs, ls] = await Promise.all([api.get<Account[]>("/money/accounts"), api.get<Loan[]>("/money/loans")]);
      setAccounts(accs.filter((a) => a.is_active)); setRows(ls);
    } catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  const current = rows.find((r) => r.id === sel) || null;
  const taken = rows.filter((r) => r.direction === "taken").reduce((s, r) => s + r.outstanding, 0);
  const given = rows.filter((r) => r.direction === "given").reduce((s, r) => s + r.outstanding, 0);

  function openAdd() {
    setAf({ direction: "taken", txn_date: today(), lender_name: "", amount: "", bank_account_id: String(accounts[0]?.id ?? ""), expected_return_date: plus3mo(), notes: "" });
    setAddOpen(true);
  }
  async function saveAdd() {
    if (!af.lender_name.trim()) { toast.warning("Enter a person's name."); return; }
    if (!(Number(af.amount) > 0)) { toast.warning("Enter an amount."); return; }
    setBusy(true);
    try {
      await api.post("/money/loans", {
        txn_date: af.txn_date, lender_name: af.lender_name.trim(), amount: Number(af.amount),
        direction: af.direction, bank_account_id: af.bank_account_id ? Number(af.bank_account_id) : null,
        expected_return_date: af.expected_return_date || null, notes: af.notes.trim() || null,
      });
      setAddOpen(false); toast.success("Loan recorded."); await load();
    } catch (e) { toast.error(errMsg(e, "Could not save.")); }
    finally { setBusy(false); }
  }
  function openRepay() {
    if (!current) { toast.warning("Select a loan first."); return; }
    if (current.outstanding <= 0) { toast.info("This loan is already settled."); return; }
    setRf({ txn_date: today(), amount: String(current.outstanding), bank_account_id: String(accounts[0]?.id ?? ""), notes: "" });
    setRepayLoan(current);
  }
  async function saveRepay() {
    if (!repayLoan) return;
    if (!(Number(rf.amount) > 0)) { toast.warning("Enter an amount."); return; }
    setBusy(true);
    try {
      await api.post(`/money/loans/${repayLoan.id}/repay`, {
        txn_date: rf.txn_date, amount: Number(rf.amount),
        bank_account_id: rf.bank_account_id ? Number(rf.bank_account_id) : null, notes: rf.notes.trim() || null,
      });
      setRepayLoan(null); toast.success("Repayment recorded."); await load();
    } catch (e) { toast.error(errMsg(e, "Could not save.")); }
    finally { setBusy(false); }
  }
  async function del() {
    if (!current) { toast.warning("Select a loan first."); return; }
    if (!(await toast.confirm({ title: "Delete loan", text: `Delete the loan (${current.lender_name}, ${money(current.principal)})?`, danger: true, okText: "Delete" }))) return;
    try { await api.del(`/money/loans/${current.id}`); setSel(null); toast.success("Deleted."); await load(); }
    catch (e) { toast.error(errMsg(e, "Could not delete.")); }
  }

  const shown = q ? rows.filter((r) => [r.lender_name, r.account_name].some((v) => (v || "").toLowerCase().includes(q.toLowerCase()))) : rows;
  const outColor = (r: Loan) => (r.outstanding <= 0 || r.direction === "given") ? "#16a34a" : "#c62828";

  return (
    <div>
      <div className="tiles" style={{ marginBottom: 12 }}>
        <Tile label="Loans taken" value={money(-taken)} color="#c62828" />
        <Tile label="Loans given" value={money(given)} color="#16a34a" />
      </div>

      <div className="md-bar">
        <div className="search-wrap"><Icon name="search" size={16} /><input className="input" placeholder="Search loans" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th>Date</th><th>Loan type</th><th style={{ textAlign: "left" }}>Person</th>
            <th className="right">Principal</th><th className="right">Repaid</th><th className="right">Outstanding</th>
            <th style={{ textAlign: "left" }}>Bank account</th><th>Expected return</th>
          </tr></thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={8} className="empty">No loans.</td></tr>}
            {shown.map((r) => (
              <tr key={r.id} onClick={() => setSel(r.id)} style={{ cursor: "pointer", ...(sel === r.id ? { background: "var(--sel-row)" } : {}) }}>
                <td>{r.txn_date}</td>
                <td>{r.direction === "given" ? "Given (lent)" : "Taken (borrowed)"}</td>
                <td>{r.lender_name}</td>
                <td className="right">{money(r.principal)}</td>
                <td className="right">{money(r.repaid)}</td>
                <td className="right" style={{ color: outColor(r), fontWeight: 600 }}>{money(r.outstanding)}</td>
                <td>{r.account_name}</td>
                <td style={{ textAlign: "center" }}>{r.expected_return_date || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="md-toolbar bottom">
        <ManageMenu actions={[
          { label: "Add", icon: "plus", run: openAdd },
          { label: "Repay", icon: "hand-coins", run: openRepay },
          "sep",
          { label: "Delete", icon: "trash", run: del, danger: true },
        ]} />
        <div className="grow" />
      </div>

      {addOpen && (
        <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setAddOpen(false); }}>
          <div className="modal">
            <div className="dlg-head"><span className="dlg-chip"><Icon name="hand-coins" size={21} /></span><span className="dlg-title">Record loan</span></div>
            <div className="modal-body">
              <Field label="Loan type">
                <select className="input" value={af.direction} onChange={(e) => setAf({ ...af, direction: e.target.value })}>
                  <option value="taken">Taken (borrowed)</option><option value="given">Given (lent)</option>
                </select>
              </Field>
              <Field label="Date"><input className="input" type="date" value={af.txn_date} onChange={(e) => setAf({ ...af, txn_date: e.target.value })} /></Field>
              <Field label="Person"><input className="input" value={af.lender_name} onChange={(e) => setAf({ ...af, lender_name: e.target.value })} /></Field>
              <Field label="Amount"><input className="input right" inputMode="decimal" value={af.amount} onChange={(e) => setAf({ ...af, amount: e.target.value })} /></Field>
              <Field label="Bank account">
                <select className="input" value={af.bank_account_id} onChange={(e) => setAf({ ...af, bank_account_id: e.target.value })}>
                  <option value="">—</option>
                  {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </Field>
              <Field label="Expected return"><input className="input" type="date" value={af.expected_return_date} onChange={(e) => setAf({ ...af, expected_return_date: e.target.value })} /></Field>
              <Field label="Notes"><input className="input" value={af.notes} onChange={(e) => setAf({ ...af, notes: e.target.value })} /></Field>
            </div>
            <div className="modal-foot">
              <button className="btn-ghost" onClick={() => setAddOpen(false)}>Cancel</button>
              <button className="btn" onClick={saveAdd} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            </div>
          </div>
        </div>
      )}

      {repayLoan && (
        <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setRepayLoan(null); }}>
          <div className="modal">
            <div className="dlg-head"><span className="dlg-chip"><Icon name="hand-coins" size={21} /></span><span className="dlg-title">Repay loan</span></div>
            <div className="modal-body">
              <p className="set-note" style={{ marginTop: 0 }}>Outstanding: <strong>{money(repayLoan.outstanding)}</strong> — {repayLoan.lender_name}</p>
              <Field label="Date"><input className="input" type="date" value={rf.txn_date} onChange={(e) => setRf({ ...rf, txn_date: e.target.value })} /></Field>
              <Field label="Amount"><input className="input right" inputMode="decimal" value={rf.amount} onChange={(e) => setRf({ ...rf, amount: e.target.value })} /></Field>
              <Field label="Bank account">
                <select className="input" value={rf.bank_account_id} onChange={(e) => setRf({ ...rf, bank_account_id: e.target.value })}>
                  <option value="">—</option>
                  {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </Field>
              <Field label="Notes"><input className="input" value={rf.notes} onChange={(e) => setRf({ ...rf, notes: e.target.value })} /></Field>
            </div>
            <div className="modal-foot">
              <button className="btn-ghost" onClick={() => setRepayLoan(null)}>Cancel</button>
              <button className="btn" onClick={saveRepay} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
