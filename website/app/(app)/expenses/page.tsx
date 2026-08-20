"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { money, today } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop ExpensesScreen (timber/ui/screens/expenses_screen.py):
   Business vs House spending. Kind + period + category filters, five stat
   cards, a table, and Add / Edit / Void via a Manage menu. Cards follow the
   desktop's expense_stats (kind + period, not category). */

type Account = { id: number; name: string; is_active: boolean };
type Expense = { id: number; txn_date: string; kind: string; category: string; amount: number; account_name: string; note: string };

const KINDS = [{ v: "", label: "All" }, { v: "business", label: "Business" }, { v: "house", label: "House" }];
const PERIODS = [
  { v: "all", label: "All" }, { v: "day", label: "Day" }, { v: "month", label: "Month" },
  { v: "year", label: "Year" }, { v: "custom", label: "Custom range" },
];
const CATEGORIES = ["rent", "electricity", "salary", "fuel", "maintenance", "other"];
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function rangeQS(p: string, from: string, to: string): string {
  const t = new Date(); const Y = t.getFullYear(); const M = t.getMonth();
  if (p === "day") return `&start=${iso(t)}&end=${iso(t)}`;
  if (p === "month") return `&start=${iso(new Date(Y, M, 1))}&end=${iso(t)}`;
  if (p === "year") return `&start=${iso(new Date(Y, 0, 1))}&end=${iso(t)}`;
  if (p === "custom") return `&start=${from}&end=${to}`;
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

const blank = (kind: string) => ({ txn_date: today(), kind: kind || "business", category: "", amount: "", bank_account_id: "", note: "" });

export default function ExpensesPage() {
  const toast = useToast();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [rows, setRows] = useState<Expense[]>([]);
  const [kind, setKind] = useState("");
  const [period, setPeriod] = useState("day");
  const [from, setFrom] = useState(() => iso(new Date()));
  const [to, setTo] = useState(() => iso(new Date()));
  const [cat, setCat] = useState("");
  const [q, setQ] = useState("");
  const [sel, setSel] = useState<number | null>(null);
  const [dialog, setDialog] = useState<null | "add" | number>(null);
  const [f, setF] = useState(blank(""));
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [accs, ex] = await Promise.all([
        api.get<Account[]>("/money/accounts"),
        api.get<Expense[]>(`/money/expenses?_=1${rangeQS(period, from, to)}`),
      ]);
      setAccounts(accs.filter((a) => a.is_active));
      setRows(ex);
    } catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
  }, [period, from, to, toast]);
  useEffect(() => { load(); }, [load]);

  // Cards follow expense_stats: kind + period filter (NOT category).
  const stats = useMemo(() => {
    const set = kind ? rows.filter((r) => r.kind === kind) : rows;
    const byCat: Record<string, number> = {};
    let total = 0, business = 0, house = 0;
    for (const r of set) {
      total += r.amount;
      if (r.kind === "house") house += r.amount; else business += r.amount;
      byCat[r.category] = (byCat[r.category] || 0) + r.amount;
    }
    const top = Object.entries(byCat).sort((a, b) => b[1] - a[1]).slice(0, 2)
      .map(([c, a]) => `${c} ${money(a)}`).join(" · ") || "—";
    return { total, business, house, count: set.length, top };
  }, [rows, kind]);

  const current = rows.find((r) => r.id === sel) || null;
  const idByName = (name: string) => accounts.find((a) => a.name === name)?.id ?? "";

  function openAdd() { setF(blank(kind)); setDialog("add"); }
  function openEdit() {
    if (!current) { toast.warning("Select an expense first."); return; }
    setF({
      txn_date: current.txn_date, kind: current.kind, category: current.category,
      amount: String(current.amount), note: current.note || "",
      bank_account_id: current.account_name === "—" ? "" : String(idByName(current.account_name)),
    });
    setDialog(current.id);
  }
  async function save() {
    if (!f.category.trim()) { toast.warning("Enter a category."); return; }
    if (!(Number(f.amount) > 0)) { toast.warning("Enter an amount."); return; }
    setBusy(true);
    const payload = {
      txn_date: f.txn_date, kind: f.kind, category: f.category.trim(), amount: Number(f.amount),
      bank_account_id: f.bank_account_id ? Number(f.bank_account_id) : null, note: f.note.trim() || null,
    };
    try {
      if (dialog === "add") await api.post("/money/expenses", payload);
      else await api.put(`/money/expenses/${dialog}`, payload);
      setDialog(null); toast.success("Saved."); await load();
    } catch (e) { toast.error(errMsg(e, "Could not save.")); }
    finally { setBusy(false); }
  }
  async function voidExpense() {
    if (!current) { toast.warning("Select an expense first."); return; }
    if (!(await toast.confirm({ title: "Void expense", text: `Void the ${current.category} expense of ${money(current.amount)}?`, danger: true, okText: "Void" }))) return;
    try { await api.post(`/money/expenses/${current.id}/void`); setSel(null); toast.success("Voided."); await load(); }
    catch (e) { toast.error(errMsg(e, "Could not void.")); }
  }

  const shown = rows.filter((r) => {
    if (kind && r.kind !== kind) return false;
    if (cat && r.category !== cat) return false;
    if (q && !`${r.category} ${r.note}`.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });

  return (
    <div>
      <div className="toolbar" style={{ alignItems: "center" }}>
        <span className="tb-lbl">Kind:</span>
        <select className="input" style={{ maxWidth: 130 }} value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map((k) => <option key={k.v} value={k.v}>{k.label}</option>)}
        </select>
        <span className="tb-lbl">Period:</span>
        <select className="input" style={{ maxWidth: 140 }} value={period} onChange={(e) => setPeriod(e.target.value)}>
          {PERIODS.map((p) => <option key={p.v} value={p.v}>{p.label}</option>)}
        </select>
        {period === "custom" && (
          <>
            <input className="input" type="date" style={{ maxWidth: 155 }} value={from} onChange={(e) => setFrom(e.target.value)} />
            <input className="input" type="date" style={{ maxWidth: 155 }} value={to} onChange={(e) => setTo(e.target.value)} />
          </>
        )}
        <span className="tb-lbl">Category:</span>
        <select className="input" style={{ maxWidth: 140, textTransform: "capitalize" }} value={cat} onChange={(e) => setCat(e.target.value)}>
          <option value="">All</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <div className="search-wrap" style={{ minWidth: 150 }}><Icon name="search" size={16} /><input className="input" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>

      <div className="tiles" style={{ margin: "0 0 12px" }}>
        <Tile label="Total expenses" value={money(stats.total)} color="#dc2626" icon="trending-down" />
        <Tile label="Business expenses" value={money(stats.business)} color="#2563eb" icon="landmark" />
        <Tile label="House expenses" value={money(stats.house)} color="#d97706" icon="receipt" />
        <Tile label="Entries" value={String(stats.count)} color="#475569" icon="database" />
        <Tile label="Top categories" value={stats.top} color="#7c3aed" icon="pie-chart" />
      </div>

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th>Date</th><th>Kind</th><th style={{ textAlign: "left" }}>Category</th>
            <th className="right">Amount</th><th style={{ textAlign: "left" }}>Bank account</th><th style={{ textAlign: "left" }}>Notes</th>
          </tr></thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={6} className="empty">No expenses.</td></tr>}
            {shown.map((r) => (
              <tr key={r.id} onClick={() => setSel(r.id)} style={{ cursor: "pointer", ...(sel === r.id ? { background: "var(--sel-row)" } : {}) }}>
                <td>{r.txn_date}</td>
                <td>{r.kind === "house" ? "House" : "Business"}</td>
                <td style={{ textTransform: "capitalize" }}>{r.category}</td>
                <td className="right">{money(r.amount)}</td>
                <td>{r.account_name}</td>
                <td>{r.note || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="md-toolbar bottom">
        <ManageMenu actions={[
          { label: "Add", icon: "plus", run: openAdd },
          { label: "Edit", icon: "pencil", run: openEdit },
          "sep",
          { label: "Void", icon: "x", run: voidExpense, danger: true },
        ]} />
        <div className="grow" />
      </div>

      {dialog !== null && (
        <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setDialog(null); }}>
          <div className="modal">
            <div className="dlg-head"><span className="dlg-chip"><Icon name="receipt" size={21} /></span><span className="dlg-title">{dialog === "add" ? "Add expense" : "Edit expense"}</span></div>
            <div className="modal-body">
              <Field label="Kind">
                <select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
                  <option value="business">Business</option><option value="house">House</option>
                </select>
              </Field>
              <Field label="Date"><input className="input" type="date" value={f.txn_date} onChange={(e) => setF({ ...f, txn_date: e.target.value })} /></Field>
              <Field label="Category">
                <input className="input" list="exp-cats" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} placeholder="rent, salary…" />
                <datalist id="exp-cats">{CATEGORIES.map((c) => <option key={c} value={c} />)}</datalist>
              </Field>
              <Field label="Amount"><input className="input right" inputMode="decimal" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
              <Field label="Bank account">
                <select className="input" value={f.bank_account_id} onChange={(e) => setF({ ...f, bank_account_id: e.target.value })}>
                  <option value="">—</option>
                  {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </Field>
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
