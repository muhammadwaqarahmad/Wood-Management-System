"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { SearchSelect } from "@/components/SearchSelect";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop FactorySplitLedgerScreen (timber/ui/screens/factory_split_screen.py):
   a factory's two-sided sub-ledger — a LEFT "Weekly" block and a RIGHT "Regular"
   block with a bold divider, three balance cards, and a Manage menu (add factory
   to the split / set per-wood rates / remove). Weekly rows show a settlement
   status (Settled, or the amount rolling to next week). */

type Factory = { id: number; name: string };
type Entry = {
  txn_date: string; kind: string; vehicle: string; wood: string; weight: number; kg: number;
  left_rate: number; left_total: number; freight: number; left_net: number;
  left_payment: number; left_balance: number;
  right_rate: number; right_amount: number; right_payment: number; right_balance: number;
  detail: string; booked_date: string | null;
};
type Statement = {
  factory_name: string; split_rate: number;
  closing_left: number; closing_right: number; closing_total: number;
  entries: Entry[];
};
type WoodRates = { woods: { id: number; name: string }[]; rates: Record<string, number> };

const PERIODS = [
  { v: "day", label: "Day" }, { v: "month", label: "Month" },
  { v: "all", label: "All" }, { v: "custom", label: "Custom range" },
];
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function rangeQS(p: string, from: string, to: string): string {
  const t = new Date(); const Y = t.getFullYear(); const M = t.getMonth();
  if (p === "day") return `&start=${iso(t)}&end=${iso(t)}`;
  if (p === "month") return `&start=${iso(new Date(Y, M, 1))}&end=${iso(t)}`;
  if (p === "custom") return `&start=${from}&end=${to}`;
  return "";
}
function weekLabel(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  const day = d.getDate();
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
  for (const [a, b] of [[1, 7], [8, 14], [15, 21], [22, last]] as const) {
    if (day >= a && day <= b) return `${a}–${b}`;
  }
  return "";
}
const kg0 = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 0 });
const DIV = { background: "#0f172a", width: 5, minWidth: 5, maxWidth: 5, padding: 0 } as const;

function Card({ label, value, color, icon }: { label: string; value: string; color: string; icon: string }) {
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
function Modal({ title, icon, onClose, children, onSave, busy, saveDisabled }: {
  title: string; icon: string; onClose: () => void; children: ReactNode; onSave?: () => void; busy?: boolean; saveDisabled?: boolean;
}) {
  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal">
        <div className="dlg-head"><span className="dlg-chip"><Icon name={icon} size={21} /></span><span className="dlg-title">{title}</span></div>
        <div className="modal-body">{children}</div>
        <div className="modal-foot">
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          {onSave && <button className="btn" onClick={onSave} disabled={busy || saveDisabled}>{busy ? "Saving…" : "Save"}</button>}
        </div>
      </div>
    </div>
  );
}

export default function FactorySubLedgerPage() {
  const toast = useToast();
  const [factories, setFactories] = useState<Factory[]>([]);
  const [fid, setFid] = useState("");
  const [period, setPeriod] = useState("day");
  const [from, setFrom] = useState(() => iso(new Date()));
  const [to, setTo] = useState(() => iso(new Date()));
  const [st, setSt] = useState<Statement | null>(null);
  const [hasRates, setHasRates] = useState(true);
  const [expOpen, setExpOpen] = useState(false);
  const expRef = useRef<HTMLDivElement>(null);
  // dialogs
  const [addOpen, setAddOpen] = useState(false);
  const [addOpts, setAddOpts] = useState<Factory[]>([]);
  const [addPick, setAddPick] = useState("");
  const [ratesOpen, setRatesOpen] = useState(false);
  const [ratesData, setRatesData] = useState<WoodRates | null>(null);
  const [rateVals, setRateVals] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    function onDoc(e: MouseEvent) { if (expRef.current && !expRef.current.contains(e.target as Node)) setExpOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const loadFactories = useCallback(async (selectId?: string) => {
    try {
      const list = await api.get<Factory[]>("/ledgers/split-factories");
      setFactories(list);
      setFid((cur) => selectId ?? (cur && list.some((f) => String(f.id) === cur) ? cur : (list[0] ? String(list[0].id) : "")));
    } catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
  }, [toast]);
  useEffect(() => { loadFactories(); }, [loadFactories]);

  const load = useCallback(async () => {
    if (!fid) { setSt(null); return; }
    try {
      const [s, wr] = await Promise.all([
        api.get<Statement>(`/ledgers/factory-split/${fid}?_=1${rangeQS(period, from, to)}`),
        api.get<WoodRates>(`/ledgers/factory-split/${fid}/wood-rates`),
      ]);
      setSt(s);
      setHasRates(Object.values(wr.rates).some((r) => r > 0));
    } catch (e) { toast.error(errMsg(e, "Couldn't load the sub-ledger.")); }
  }, [fid, period, from, to, toast]);
  useEffect(() => { load(); }, [load]);

  async function doExport(fmt: "pdf" | "xlsx") {
    setExpOpen(false);
    if (!fid) { toast.warning("Choose a factory first."); return; }
    try { await api.download(`/ledgers/factory-split/${fid}/export?fmt=${fmt}${rangeQS(period, from, to)}`, `factory_sub_ledger.${fmt}`); }
    catch (e) { toast.error(errMsg(e, "Export failed.")); }
  }

  async function openAdd() {
    try {
      const all = await api.get<{ id: number; name: string }[]>("/parties?kind=factory");
      const enrolled = new Set(factories.map((f) => f.id));
      const avail = all.filter((f) => !enrolled.has(f.id)).map((f) => ({ id: f.id, name: f.name }));
      if (avail.length === 0) { toast.info("All factories are already enrolled."); return; }
      setAddOpts(avail); setAddPick(""); setAddOpen(true);
    } catch (e) { toast.error(errMsg(e, "Failed.")); }
  }
  async function saveAdd() {
    if (!addPick) { toast.warning("Pick a factory."); return; }
    setBusy(true);
    try { await api.post(`/ledgers/factory-split/${addPick}/enroll`, {}); setAddOpen(false); toast.success("Factory added to the split."); await loadFactories(addPick); }
    catch (e) { toast.error(errMsg(e, "Failed.")); }
    finally { setBusy(false); }
  }
  async function openRates() {
    if (!fid) { toast.warning("Choose a factory first."); return; }
    try {
      const wr = await api.get<WoodRates>(`/ledgers/factory-split/${fid}/wood-rates`);
      setRatesData(wr);
      setRateVals(Object.fromEntries(wr.woods.map((w) => [String(w.id), String(wr.rates[String(w.id)] ?? 0)])));
      setRatesOpen(true);
    } catch (e) { toast.error(errMsg(e, "Failed.")); }
  }
  async function saveRates() {
    setBusy(true);
    try {
      const rates = Object.fromEntries(Object.entries(rateVals).map(([k, v]) => [k, Number(v) || 0]));
      await api.post(`/ledgers/factory-split/${fid}/rates`, { rates });
      setRatesOpen(false); toast.success("Split rates saved."); await load();
    } catch (e) { toast.error(errMsg(e, "Failed.")); }
    finally { setBusy(false); }
  }
  async function removeFactory() {
    const name = factories.find((f) => String(f.id) === fid)?.name ?? "this factory";
    if (!(await toast.confirm({ title: "Remove from split", text: `Remove "${name}" from the split ledger?`, danger: true, okText: "Remove" }))) return;
    try { await api.del(`/ledgers/factory-split/${fid}`); toast.success("Removed."); setFid(""); await loadFactories(); }
    catch (e) { toast.error(errMsg(e, "Failed.")); }
  }

  const factoryOpts = factories.map((f) => ({ value: String(f.id), label: f.name }));
  const noFactories = factories.length === 0;
  const status = (bal: number) => bal === 0 ? "Settled" : bal > 0 ? `${money(bal)} →` : money(bal);

  return (
    <div>
      <div className="toolbar" style={{ alignItems: "center" }}>
        <span className="tb-lbl">Factory:</span>
        <div style={{ minWidth: 240 }}><SearchSelect value={fid} options={factoryOpts} onChange={setFid} placeholder="Search factory…" /></div>
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
        <ManageMenu actions={[
          { label: "Add factory", icon: "plus", run: openAdd },
          { label: "Set split rates", icon: "pencil", run: openRates },
          "sep",
          { label: "Remove from split", icon: "trash", run: removeFactory, danger: true },
        ]} />
      </div>

      <div className="tiles" style={{ margin: "0 0 12px" }}>
        <Card label="Weekly balance" value={st ? money(st.closing_left) : "—"} color="#2563eb" icon="calendar-clock" />
        <Card label="Regular balance" value={st ? money(st.closing_right) : "—"} color="#7c3aed" icon="wallet" />
        <Card label="Combined balance" value={st ? money(st.closing_total) : "—"} color="#0d9488" icon="pie-chart" />
      </div>

      {(noFactories || (fid && !hasRates)) && (
        <div className="card notice" style={{ marginBottom: 12, borderColor: "#d97706" }}>
          <p className="set-note" style={{ color: "#d97706", fontWeight: 600, margin: 0 }}>
            {noFactories
              ? "No factory uses the split ledger yet. Use Manage → Add factory to enrol one."
              : "Set per-wood split rates (Manage → Set split rates) to activate this factory's sub-ledger."}
          </p>
        </div>
      )}

      {fid && st && (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th colSpan={4}></th>
                <th colSpan={9} style={{ background: "color-mix(in srgb, #2563eb 12%, transparent)" }}>Weekly</th>
                <th style={DIV}></th>
                <th colSpan={6} style={{ background: "color-mix(in srgb, #7c3aed 12%, transparent)" }}>Regular</th>
              </tr>
              <tr>
                <th style={{ textAlign: "left" }}>Date</th><th>Week</th><th style={{ textAlign: "left" }}>Vehicle</th><th style={{ textAlign: "left" }}>Wood</th>
                <th className="right">Rate</th><th className="right">Weight</th><th className="right">Kg</th><th className="right">Total</th><th className="right">Freight</th><th className="right">Sale</th><th className="right">Payment</th><th className="right">Balance</th><th>Weekly status</th>
                <th style={DIV}></th>
                <th className="right">Rate</th><th className="right">Weight</th><th className="right">Kg</th><th className="right">Total</th><th className="right">Payment</th><th className="right">Balance</th>
              </tr>
            </thead>
            <tbody>
              {st.entries.length === 0 && <tr><td colSpan={20} className="empty">No entries in this period.</td></tr>}
              {st.entries.map((e, i) => {
                const isLoad = e.kind === "load";
                const settled = e.left_balance === 0;
                return (
                  <tr key={i}>
                    <td>{e.txn_date}{e.booked_date && e.booked_date !== e.txn_date ? <div className="set-note" style={{ margin: 0 }}>Entry: {e.booked_date}</div> : null}</td>
                    <td style={{ textAlign: "center" }}>{weekLabel(e.txn_date)}</td>
                    <td>{isLoad ? (e.vehicle || "—") : ""}</td>
                    <td>{isLoad ? (e.wood || "—") : ""}</td>
                    {/* weekly block */}
                    <td className="right">{isLoad ? money(e.left_rate) : ""}</td>
                    <td className="right">{isLoad ? money(e.weight) : ""}</td>
                    <td className="right">{isLoad ? kg0(e.kg) : ""}</td>
                    <td className="right">{isLoad ? money(e.left_total) : ""}</td>
                    <td className="right">{isLoad && e.freight ? money(e.freight) : ""}</td>
                    <td className="right">{isLoad ? money(e.left_net) : ""}</td>
                    <td className="right" style={{ color: !isLoad && e.left_payment ? "#2e7d32" : undefined }}>{!isLoad && e.left_payment ? money(e.left_payment) : ""}</td>
                    <td className="right" style={{ color: e.left_balance < 0 ? "#c62828" : "#2e7d32" }}>{money(e.left_balance)}</td>
                    <td style={{ textAlign: "center", color: settled ? "#059669" : "#e11d48", fontWeight: 600 }}>{status(e.left_balance)}</td>
                    <td style={DIV}></td>
                    {/* regular block */}
                    <td className="right">{isLoad ? money(e.right_rate) : ""}</td>
                    <td className="right">{isLoad ? money(e.weight) : ""}</td>
                    <td className="right">{isLoad ? kg0(e.kg) : ""}</td>
                    <td className="right">{isLoad ? money(e.right_amount) : ""}</td>
                    <td className="right" style={{ color: !isLoad && e.right_payment ? "#2e7d32" : undefined }}>{!isLoad && e.right_payment ? money(e.right_payment) : ""}</td>
                    <td className="right" style={{ color: e.right_balance < 0 ? "#c62828" : "#2e7d32" }}>{money(e.right_balance)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {addOpen && (
        <Modal title="Add factory" icon="factory" onClose={() => setAddOpen(false)} onSave={saveAdd} busy={busy}>
          <label className="fld"><span>Factory</span>
            <SearchSelect value={addPick} options={addOpts.map((f) => ({ value: String(f.id), label: f.name }))} onChange={setAddPick} placeholder="Search factory…" />
          </label>
          <p className="set-note" style={{ marginTop: 6 }}>Enrols the factory in the split ledger. Set its per-wood rates next.</p>
        </Modal>
      )}

      {ratesOpen && ratesData && (
        <Modal title="Set split rates" icon="pencil" onClose={() => setRatesOpen(false)} onSave={saveRates} busy={busy} saveDisabled={ratesData.woods.length === 0}>
          <p className="set-note" style={{ marginTop: 0 }}>The regular (irregular) rate per wood type. 0 keeps the whole rate on the weekly side.</p>
          {ratesData.woods.length === 0
            ? <p className="muted">This factory hasn&apos;t traded any wood yet.</p>
            : ratesData.woods.map((w) => (
              <label className="fld" key={w.id}><span>{w.name}</span>
                <input className="input right" inputMode="decimal" value={rateVals[String(w.id)] ?? ""} onChange={(ev) => setRateVals({ ...rateVals, [String(w.id)]: ev.target.value })} />
              </label>
            ))}
        </Modal>
      )}
    </div>
  );
}
