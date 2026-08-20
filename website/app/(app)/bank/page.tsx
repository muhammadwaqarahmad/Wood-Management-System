"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";
import { useAuth } from "@/lib/auth";

/* Mirrors the desktop BankAccountsScreen (timber/ui/screens/bank_accounts_screen.py):
   three KPI tiles (Cash position / Cheque balance / Loans payable), a searchable
   table (Name, Bank name, Account number, IBAN, Branch, Today's opening, Closing),
   and a Manage menu (Add / Edit). Opening balance is Admin-only, like the desktop. */

type Account = {
  id: number; name: string; closing: number; is_cash: boolean; is_active: boolean;
  bank_name: string | null; account_number: string | null;
  iban: string | null; branch: string | null; opening: number; opening_today: number;
};
type Summary = { cash_position: number; cheque_balance: number; total_loans: number };
type Detail = {
  name_en: string; name_ur: string; bank_name: string; account_number: string;
  iban: string; branch: string; opening_balance: number;
};

const BLANK = { name_en: "", name_ur: "", bank_name: "", account_number: "", iban: "", branch: "", opening_balance: "" };
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);

/* ------------------------------------------------------------ Manage menu -- */
type Action = { label: string; icon: string; run: () => void };
function ManageMenu({ actions }: { actions: Action[] }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onDoc(e: MouseEvent) { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);
  return (
    <div className="manage" ref={ref}>
      <button className="manage-btn" onClick={() => setOpen((o) => !o)}>
        <Icon name="settings" size={15} /> Manage ▾
      </button>
      {open && (
        <div className="manage-menu up">
          {actions.map((a) => (
            <button key={a.label} className="manage-item" onClick={() => { setOpen(false); a.run(); }}>
              <Icon name={a.icon} size={16} /> {a.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Tile({ label, value, color, icon }: { label: string; value: number; color: string; icon: string }) {
  return (
    <div className="tile" style={{ borderLeftColor: color }}>
      <div className="cap">
        <span className="chip" style={{ background: `linear-gradient(135deg, ${color}, color-mix(in srgb, ${color} 60%, #fff))` }}>
          <Icon name={icon} size={16} />
        </span>
        {label}
      </div>
      <div className="val">{money(value)}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="fld"><span>{label}</span>{children}</label>;
}

export default function BankPage() {
  const toast = useToast();
  const { user } = useAuth();
  const isAdmin = user?.role === "Admin";

  const [rows, setRows] = useState<Account[]>([]);
  const [sum, setSum] = useState<Summary>({ cash_position: 0, cheque_balance: 0, total_loans: 0 });
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const [dialog, setDialog] = useState<null | "add" | number>(null);
  const [f, setF] = useState({ ...BLANK });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [acc, s] = await Promise.all([
        api.get<Account[]>("/money/accounts?include_inactive=true"),
        api.get<Summary>("/money/summary"),
      ]);
      setRows(acc); setSum(s);
    } catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  const current = rows.find((r) => r.id === sel) || null;
  function requireSel(): Account | null { if (!current) { toast.warning("Select an account first."); return null; } return current; }

  function openAdd() { setF({ ...BLANK }); setDialog("add"); }
  async function openEdit() {
    const a = requireSel(); if (!a) return;
    try {
      const d = await api.get<Detail>(`/money/accounts/${a.id}`);
      setF({
        name_en: d.name_en || "", name_ur: d.name_ur || "", bank_name: d.bank_name || "",
        account_number: d.account_number || "", iban: d.iban || "", branch: d.branch || "",
        opening_balance: String(d.opening_balance ?? ""),
      });
      setDialog(a.id);
    } catch (e) { toast.error(errMsg(e, "Could not load.")); }
  }

  async function save() {
    if (!f.name_en.trim() && !f.name_ur.trim()) { toast.warning("Enter a name."); return; }
    const iban = f.iban.trim();
    if (iban && iban.length !== 24) { toast.warning("IBAN must be exactly 24 characters."); return; }
    setBusy(true);
    const payload = {
      name_en: f.name_en.trim() || null, name_ur: f.name_ur.trim() || null,
      bank_name: f.bank_name.trim() || null, account_number: f.account_number.trim() || null,
      iban: iban || null, branch: f.branch.trim() || null,
      // Non-admins can't change the opening balance — omit it so the server keeps it.
      ...(isAdmin ? { opening_balance: Number(f.opening_balance) || 0 } : {}),
    };
    try {
      if (dialog === "add") await api.post("/money/accounts", payload);
      else await api.put(`/money/accounts/${dialog}`, payload);
      setDialog(null); toast.success("Saved."); await load();
    } catch (e) { toast.error(errMsg(e, "Could not save.")); }
    finally { setBusy(false); }
  }

  const shown = q
    ? rows.filter((a) => [a.name, a.bank_name, a.account_number, a.iban, a.branch]
        .some((v) => (v || "").toLowerCase().includes(q.toLowerCase())))
    : rows;

  return (
    <div>
      <div className="tiles" style={{ marginBottom: 12 }}>
        <Tile label="Cash position" value={sum.cash_position} color="#6366f1" icon="wallet" />
        <Tile label="Cheque balance" value={sum.cheque_balance} color="#f59e0b" icon="file-check" />
        <Tile label="Loans payable" value={sum.total_loans} color="#8b5cf6" icon="hand-coins" />
      </div>

      <div className="md-bar">
        <div className="search-wrap"><Icon name="search" size={16} /><input className="input" placeholder="Search accounts" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th style={{ textAlign: "left" }}>Name</th><th style={{ textAlign: "left" }}>Bank name</th>
            <th>Account number</th><th>IBAN</th><th>Branch / location</th>
            <th className="right">Today&apos;s opening</th><th className="right">Closing</th>
          </tr></thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={7} className="empty">No accounts.</td></tr>}
            {shown.map((a) => (
              <tr key={a.id} onClick={() => setSel(a.id)}
                style={{ cursor: "pointer", ...(sel === a.id ? { background: "var(--sel-row)" } : {}), ...(a.is_active ? {} : { opacity: 0.55 }) }}>
                <td>{a.name}</td>
                <td>{a.bank_name || "—"}</td>
                <td>{a.account_number || "—"}</td>
                <td>{a.iban || "—"}</td>
                <td>{a.branch || "—"}</td>
                <td className="right">{money(a.opening_today)}</td>
                <td className="right">{money(a.closing)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="md-toolbar bottom">
        <ManageMenu actions={[
          { label: "Add", icon: "plus", run: openAdd },
          { label: "Edit", icon: "pencil", run: openEdit },
        ]} />
        <div className="grow" />
      </div>

      {dialog !== null && (
        <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setDialog(null); }}>
          <div className="modal">
            <div className="dlg-head">
              <span className="dlg-chip"><Icon name="landmark" size={21} /></span>
              <span className="dlg-title">{dialog === "add" ? "Add account" : "Edit account"}</span>
            </div>
            <div className="modal-body">
              <Field label="Name (English)"><input className="input" value={f.name_en} onChange={(e) => setF({ ...f, name_en: e.target.value })} /></Field>
              <Field label="Name (Urdu)"><input className="input" value={f.name_ur} onChange={(e) => setF({ ...f, name_ur: e.target.value })} /></Field>
              <Field label="Bank name"><input className="input" value={f.bank_name} onChange={(e) => setF({ ...f, bank_name: e.target.value })} /></Field>
              <Field label="Account number"><input className="input" value={f.account_number} onChange={(e) => setF({ ...f, account_number: e.target.value })} /></Field>
              <Field label="IBAN"><input className="input" maxLength={24} value={f.iban} onChange={(e) => setF({ ...f, iban: e.target.value })} /></Field>
              <Field label="Branch / location"><input className="input" value={f.branch} onChange={(e) => setF({ ...f, branch: e.target.value })} /></Field>
              <Field label="Opening balance">
                <input className="input right" inputMode="decimal" value={f.opening_balance} disabled={!isAdmin}
                  onChange={(e) => setF({ ...f, opening_balance: e.target.value })} />
                {!isAdmin && <p className="set-note" style={{ margin: "4px 0 0", color: "var(--muted)" }}>Only an Admin can set or change the opening balance.</p>}
              </Field>
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
