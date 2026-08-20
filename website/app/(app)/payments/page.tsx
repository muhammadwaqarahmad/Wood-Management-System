"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { SearchSelect } from "@/components/SearchSelect";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop PaymentEntryScreen (timber/ui/screens/payment_entry.py):
   Factory + Supplier tabs; each has a "Record payment" modal (party side + our
   side) and a history table. Factory = money received; Supplier = money paid. */

type Party = { id: number; name: string; balance: number };
type Account = { id: number; name: string; closing: number };
type Bank = { id: number; account_title: string; bank_name: string };
type Row = { id: number; txn_date: string; party_name: string; amount: number; method: string; account_name: string; party_account: string; reference: string };

const METHODS = [
  { v: "cash", label: "Cash" }, { v: "online", label: "Online" },
  { v: "bank", label: "Bank" }, { v: "cheque", label: "Cheque" },
];
const today = () => new Date().toISOString().slice(0, 10);
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);

export default function PaymentsPage() {
  const [tab, setTab] = useState<"factory" | "supplier">("factory");
  return (
    <div>
      <div className="md-tabs">
        <button className={"md-tab" + (tab === "factory" ? " on" : "")} onClick={() => setTab("factory")}>
          <Icon name="factory" size={16} /> Factory
        </button>
        <button className={"md-tab" + (tab === "supplier" ? " on" : "")} onClick={() => setTab("supplier")}>
          <Icon name="book-user" size={16} /> Supplier
        </button>
      </div>
      <Panel key={tab} kind={tab} />
    </div>
  );
}

function blankForm(kind: "factory" | "supplier") {
  return {
    partyId: "", received: today(), entry: today(),
    direction: kind === "factory" ? "in" : "out",   // natural direction
    amount: "", method: "cash", accountId: "", partyBankId: "", reference: "",
    splitSide: "left",   // factory split sub-ledger: Weekly (left) / Regular (right)
  };
}

const SPLIT_SIDES = [
  { v: "left", label: "Weekly" },
  { v: "right", label: "Regular payment" },
];

function Panel({ kind }: { kind: "factory" | "supplier" }) {
  const toast = useToast();
  const isFactory = kind === "factory";
  const [rows, setRows] = useState<Row[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [f, setF] = useState(blankForm(kind));
  const [partyBanks, setPartyBanks] = useState<Bank[]>([]);
  const [splitEnrolled, setSplitEnrolled] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [pm, pt, ac] = await Promise.all([
        api.get<{ payments: Row[] }>(`/payments?kind=${kind}`),
        api.get<Party[]>(`/parties?kind=${kind}`),
        api.get<Account[]>("/money/accounts"),
      ]);
      setRows(pm.payments.slice().reverse()); setParties(pt); setAccounts(ac);
    } catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
  }, [kind, toast]);
  useEffect(() => { load(); }, [load]);

  async function onParty(id: string) {
    setF((s) => ({ ...s, partyId: id, partyBankId: "" }));
    setPartyBanks([]); setSplitEnrolled(false);
    if (!id) return;
    try {
      const d = await api.get<{ banks: Bank[]; split_enrolled?: boolean }>(`/parties/${id}`);
      setPartyBanks(d.banks || []);
      setSplitEnrolled(!!d.split_enrolled);
    } catch { /* banks are optional */ }
  }

  const current = parties.find((p) => p.id === Number(f.partyId));
  const balDisp = current ? (isFactory ? current.balance : -current.balance) : 0;
  const acct = accounts.find((a) => a.id === Number(f.accountId));

  function openForm() { setF(blankForm(kind)); setPartyBanks([]); setSplitEnrolled(false); setOpen(true); }

  // "Which side" selector: factory-only, and only for factories enrolled in the
  // weekly/irregular split sub-ledger (mirrors the desktop payment form).
  const showSide = isFactory && splitEnrolled;

  async function save() {
    if (!f.partyId) { toast.warning("Select a party."); return; }
    if (!(Number(f.amount) > 0)) { toast.warning("Enter an amount."); return; }
    setBusy(true);
    try {
      await api.post("/payments", {
        txn_date: f.received, entry_date: f.entry, party_id: Number(f.partyId),
        amount: Number(f.amount), direction: f.direction, method: f.method,
        bank_account_id: f.accountId ? Number(f.accountId) : null,
        party_bank_id: f.partyBankId ? Number(f.partyBankId) : null,
        reference_no: f.reference.trim() || null,
        split_side: showSide ? f.splitSide : null,
      });
      setOpen(false); toast.success("Payment recorded."); await load();
    } catch (e) { toast.error(errMsg(e, "Could not save.")); }
    finally { setBusy(false); }
  }
  async function voidPayment(r: Row) {
    if (!(await toast.confirm({ title: "Void payment", text: `Void the payment of ${money(r.amount)} to ${r.party_name}?`, danger: true, okText: "Void" }))) return;
    try { await api.post(`/payments/${r.id}/void`); toast.success("Voided."); await load(); }
    catch (e) { toast.error(errMsg(e, "Could not void.")); }
  }

  const shown = q ? rows.filter((r) => r.party_name.toLowerCase().includes(q.toLowerCase()) || r.reference.toLowerCase().includes(q.toLowerCase())) : rows;
  const partyOpts = parties.map((p) => ({ value: String(p.id), label: p.name }));

  return (
    <div>
      <div className="md-bar">
        <div className="search-wrap"><Icon name="search" size={16} /><input className="input" placeholder="Search payments" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <div className="grow" />
        <button className="btn" onClick={openForm}><Icon name="plus" size={15} /> Record payment</button>
      </div>

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th>Date</th><th style={{ textAlign: "left" }}>Name</th><th className="right">Amount</th>
            <th>Method</th><th>Bank account</th><th>Party account</th><th>Reference</th><th />
          </tr></thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={8} className="empty">No payments yet.</td></tr>}
            {shown.map((r) => (
              <tr key={r.id}>
                <td>{r.txn_date}</td>
                <td>{r.party_name}</td>
                <td className="right">{money(r.amount)}</td>
                <td style={{ textTransform: "capitalize" }}>{r.method}</td>
                <td>{r.account_name}</td>
                <td>{r.party_account || "—"}</td>
                <td>{r.reference || "—"}</td>
                <td className="right"><button className="btn-ghost" onClick={() => voidPayment(r)}>Void</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {open && (
        <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
          <div className="modal wide">
            <div className="dlg-head">
              <span className="dlg-chip"><Icon name="wallet" size={21} /></span>
              <span className="dlg-title">Record payment — {isFactory ? "Factory" : "Supplier"}</span>
            </div>
            <div className="modal-body">
              <div className="grid2">
                {/* Party side */}
                <div className="gbox">
                  <div className="gbox-title">{isFactory ? "Factory" : "Supplier"}</div>
                  <Field label="Received date"><input className="input" type="date" value={f.received} onChange={(e) => setF({ ...f, received: e.target.value })} /></Field>
                  <Field label="Entry date"><input className="input" type="date" value={f.entry} onChange={(e) => setF({ ...f, entry: e.target.value })} /></Field>
                  <Field label="Name"><SearchSelect value={f.partyId} options={partyOpts} onChange={onParty} /></Field>
                  <Field label="Current balance">
                    <div className="bal-line" style={{ color: balDisp > 0 ? "var(--pos)" : balDisp < 0 ? "var(--neg)" : "var(--muted)" }}>
                      {current ? money(balDisp) : "—"}
                    </div>
                  </Field>
                  <Field label={`${isFactory ? "Factory" : "Supplier"} account`}>
                    <select className="input" value={f.partyBankId} onChange={(e) => setF({ ...f, partyBankId: e.target.value })}>
                      <option value="">—</option>
                      {partyBanks.map((b) => <option key={b.id} value={b.id}>{[b.account_title, b.bank_name].filter(Boolean).join(" — ") || `#${b.id}`}</option>)}
                    </select>
                  </Field>
                  {showSide && (
                    <Field label="Which side">
                      <select className="input" value={f.splitSide} onChange={(e) => setF({ ...f, splitSide: e.target.value })}>
                        {SPLIT_SIDES.map((s) => <option key={s.v} value={s.v}>{s.label}</option>)}
                      </select>
                    </Field>
                  )}
                </div>
                {/* Our side */}
                <div className="gbox">
                  <div className="gbox-title">Abdul Sattar Woods</div>
                  <Field label="Direction">
                    <div className="seg-dir">
                      <button className={"btn-ghost" + (f.direction === "out" ? " split-on" : "")} onClick={() => setF({ ...f, direction: "out" })}>We Paid</button>
                      <button className={"btn-ghost" + (f.direction === "in" ? " split-on" : "")} onClick={() => setF({ ...f, direction: "in" })}>We Received</button>
                    </div>
                  </Field>
                  <Field label="Amount"><input className="input" inputMode="decimal" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
                  <Field label="Method">
                    <select className="input" value={f.method} onChange={(e) => setF({ ...f, method: e.target.value })}>
                      {METHODS.map((m) => <option key={m.v} value={m.v}>{m.label}</option>)}
                    </select>
                  </Field>
                  <Field label="Bank account">
                    <select className="input" value={f.accountId} onChange={(e) => setF({ ...f, accountId: e.target.value })}>
                      <option value="">—</option>
                      {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                    </select>
                    {acct && <p className="set-note" style={{ margin: "4px 0 0", color: "var(--accent)" }}>Available: {money(acct.closing)}</p>}
                  </Field>
                  <Field label="Reference"><input className="input" value={f.reference} onChange={(e) => setF({ ...f, reference: e.target.value })} /></Field>
                </div>
              </div>
            </div>
            <div className="modal-foot">
              <button className="btn-ghost" onClick={() => setOpen(false)}>Cancel</button>
              <button className="btn" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="fld" style={{ marginBottom: 12 }}><span>{label}</span>{children}</label>;
}
