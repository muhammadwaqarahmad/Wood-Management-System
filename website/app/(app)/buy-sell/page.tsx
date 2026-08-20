"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { SearchSelect } from "@/components/SearchSelect";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop BuySellScreen (timber/ui/screens/buy_sell_screen.py):
   General details, wood-inventory rows (factory/supplier weight + rate, kg
   calculator, wood pre-fills rates), logistics costs (per-charge payer + split),
   a pinned dark totals bar, and the same purchase/sale/net/profit math. Saves
   through POST /trades (create_mixed_trade). */

type Party = { id: number; name: string; balance: number };
type Wood = { id: number; name: string; default_supplier_rate: number; default_factory_rate: number };
type Row = { id: number; wood: string; facW: string; facR: string; supW: string; supR: string };
type Payer = "us" | "factory" | "bapari";
type Charge = { amount: string; payer: Payer; splitOn: boolean; split: string; payer2: Payer };

const PAYERS: { v: Payer; label: string }[] = [
  { v: "us", label: "Us" }, { v: "factory", label: "Factory" }, { v: "bapari", label: "Supplier" },
];
const n = (s: string) => parseFloat(s) || 0;
const blankCharge = (): Charge => ({ amount: "", payer: "factory", splitOn: false, split: "", payer2: "us" });
const blankRow = (id: number): Row => ({ id, wood: "", facW: "", facR: "", supW: "", supR: "" });

export default function BuySellPage() {
  const toast = useToast();
  const [today] = useState(() => new Date().toISOString().slice(0, 10));
  const [date, setDate] = useState(today);
  const [vehicle, setVehicle] = useState("");
  const [supplierId, setSupplierId] = useState("");
  const [factoryId, setFactoryId] = useState("");

  const [suppliers, setSuppliers] = useState<Party[]>([]);
  const [factories, setFactories] = useState<Party[]>([]);
  const [woods, setWoods] = useState<Wood[]>([]);
  const woodRate = useMemo(() => {
    const m = new Map<number, { sup: number; fac: number }>();
    woods.forEach((w) => m.set(w.id, { sup: w.default_supplier_rate || 0, fac: w.default_factory_rate || 0 }));
    return m;
  }, [woods]);
  const supOpts = useMemo(() => suppliers.map((p) => ({ value: String(p.id), label: p.name })), [suppliers]);
  const facOpts = useMemo(() => factories.map((p) => ({ value: String(p.id), label: p.name })), [factories]);
  const woodOpts = useMemo(() => woods.map((w) => ({ value: String(w.id), label: w.name })), [woods]);

  const [rid, setRid] = useState(2);
  const [rows, setRows] = useState<Row[]>([blankRow(1)]);
  const [loading, setLoading] = useState<Charge>(blankCharge());
  const [freight, setFreight] = useState<Charge>(blankCharge());
  const [unloading, setUnloading] = useState<Charge>(blankCharge());
  const [saving, setSaving] = useState(false);
  const [banner, setBanner] = useState<{ ok: boolean; msg: string } | null>(null);
  const [kg, setKg] = useState<{ rowId: number } | null>(null);

  const load = useCallback(async () => {
    try {
      const [sup, fac, wd] = await Promise.all([
        api.get<Party[]>("/parties?kind=supplier"),
        api.get<Party[]>("/parties?kind=factory"),
        api.get<{ wood_types: Wood[] }>("/master/wood-types"),
      ]);
      setSuppliers(sup); setFactories(fac); setWoods(wd.wood_types);
    } catch (e) { toast.error(e instanceof ApiError ? e.message : "Couldn't reach the API."); }
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  // ---- row helpers ----
  function patchRow(id: number, p: Partial<Row>) {
    setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...p } : r)));
  }
  function onWood(id: number, wid: string) {
    const rates = woodRate.get(Number(wid));
    setRows((rs) => rs.map((r) => {
      if (r.id !== id) return r;
      const next = { ...r, wood: wid };
      if (rates) {                                   // pre-fill a rate only if still empty
        if (rates.sup > 0 && !n(r.supR)) next.supR = String(rates.sup);
        if (rates.fac > 0 && !n(r.facR)) next.facR = String(rates.fac);
      }
      return next;
    }));
  }
  function onFacW(id: number, v: string) {           // supplier weight follows trunc(factory weight)
    patchRow(id, { facW: v, supW: String(Math.trunc(n(v))) });
  }
  function addRow() { setRows((rs) => [...rs, blankRow(rid)]); setRid((x) => x + 1); }
  function delRow(id: number) { setRows((rs) => (rs.length <= 1 ? rs : rs.filter((r) => r.id !== id))); }
  function applyKg(mode: "weight" | "rate", value: number) {
    if (!kg) return;
    if (mode === "weight") patchRow(kg.rowId, { facW: String(value / 40), supW: String(Math.trunc(value / 40)) });
    else patchRow(kg.rowId, { facR: String(value * 40) });
    setKg(null);
  }

  // ---- totals (same math as _recalc) ----
  const t = useMemo(() => {
    let purchase = 0, sale = 0;
    for (const r of rows) { purchase += n(r.supW) * n(r.supR); sale += n(r.facW) * n(r.facR); }
    const by = { us: 0, factory: 0, bapari: 0 };
    for (const c of [loading, freight, unloading]) {
      const amt = n(c.amount); if (!amt) continue;
      const sp = n(c.split);
      if (c.splitOn && sp > 0 && sp < amt) { by[c.payer] += sp; by[c.payer2] += amt - sp; }
      else by[c.payer] += amt;
    }
    const freightTotal = n(loading.amount) + n(freight.amount) + n(unloading.amount);
    return {
      purchase, sale, freightTotal,
      supplierNet: purchase - (by.factory + by.us),
      factoryNet: sale - by.factory,
      profit: sale - purchase,
    };
  }, [rows, loading, freight, unloading]);

  function chargePayload(c: Charge) {
    const amt = n(c.amount), sp = n(c.split);
    const split = c.splitOn && sp > 0 && sp < amt;
    return { amount: amt, payer: c.payer, payer2: split ? c.payer2 : null, split: split ? sp : 0 };
  }

  async function save() {
    if (!supplierId || !factoryId) { toast.warning("Select a supplier and a factory."); return; }
    setBanner(null); setSaving(true);
    const L = chargePayload(loading), F = chargePayload(freight), U = chargePayload(unloading);
    const payload = {
      txn_date: date, bapari_id: Number(supplierId), factory_id: Number(factoryId),
      vehicle_no: vehicle.trim() || null,
      lines: rows.map((r) => ({
        wood_type_id: r.wood ? Number(r.wood) : null,
        muds: n(r.supW), kg: 0, bapari_rate: n(r.supR),
        factory_rate: n(r.facR), factory_muds: n(r.facW), factory_kg: 0,
      })),
      loading_amount: L.amount, loading_payer: L.payer, loading_payer2: L.payer2, loading_split: L.split,
      freight_amount: F.amount, freight_payer: F.payer, freight_payer2: F.payer2, freight_split: F.split,
      unloading_amount: U.amount, unloading_payer: U.payer, unloading_payer2: U.payer2, unloading_split: U.split,
    };
    try {
      const r = await api.post<{ count: number }>("/trades", payload);
      const msg = `Saved — ${r.count} wood line${r.count === 1 ? "" : "s"}, profit ${money(t.profit)}`;
      setBanner({ ok: true, msg }); toast.success(msg);
      reset(); await load();
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Could not save.";
      setBanner({ ok: false, msg }); toast.error(msg);
    } finally { setSaving(false); }
  }
  function reset() {
    setRows([blankRow(rid)]); setRid((x) => x + 1);
    setVehicle("");
    setLoading(blankCharge()); setFreight(blankCharge()); setUnloading(blankCharge());
  }

  const supBadge = balanceBadge(suppliers, supplierId, true);
  const facBadge = balanceBadge(factories, factoryId, false);

  return (
    <div className="bs-wrap">
      {/* General details */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head"><span className="chip"><Icon name="calendar-clock" size={15} /></span><span className="h">General Details</span></div>
        <div className="bs-fields">
          <Field label="Date"><input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
          <Field label="Vehicle no."><input className="input" placeholder="LEA-1234" value={vehicle} onChange={(e) => setVehicle(e.target.value)} /></Field>
          <Field label="Supplier" badge={supBadge}>
            <SearchSelect value={supplierId} options={supOpts} onChange={setSupplierId} />
          </Field>
          <Field label="Factory" badge={facBadge}>
            <SearchSelect value={factoryId} options={facOpts} onChange={setFactoryId} />
          </Field>
        </div>
      </div>

      {/* Wood inventory */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head"><span className="chip"><Icon name="receipt" size={15} /></span><span className="h">Wood Inventory Details</span></div>
        <div className="wood-grid wood-head">
          <span>Wood type</span><span>Factory weight</span><span>Factory rate</span><span>Kg</span>
          <span>Supplier weight</span><span>Supplier rate</span><span />
        </div>
        {rows.map((r) => (
          <div className="wood-grid wood-row" key={r.id}>
            <SearchSelect value={r.wood} options={woodOpts} onChange={(v) => onWood(r.id, v)} />
            <input className="input" inputMode="decimal" value={r.facW} onChange={(e) => onFacW(r.id, e.target.value)} />
            <input className="input" inputMode="decimal" value={r.facR} onChange={(e) => patchRow(r.id, { facR: e.target.value })} />
            <button className="kg-btn" onClick={() => setKg({ rowId: r.id })}>Kg</button>
            <input className="input" inputMode="decimal" value={r.supW} onChange={(e) => patchRow(r.id, { supW: e.target.value })} />
            <input className="input" inputMode="decimal" value={r.supR} onChange={(e) => patchRow(r.id, { supR: e.target.value })} />
            <button className="del-x" onClick={() => delRow(r.id)} aria-label="Remove"><Icon name="x" size={15} /></button>
          </div>
        ))}
        <div style={{ marginTop: 12 }}>
          <button className="btn-dark" onClick={addRow}><Icon name="plus" size={15} /> Add wood</button>
        </div>
      </div>

      {/* Logistics costs */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head"><span className="chip"><Icon name="wallet" size={15} /></span><span className="h">Logistics Costs</span></div>
        <ChargeRow label="Loading" c={loading} set={setLoading} />
        <ChargeRow label="Freight" c={freight} set={setFreight} />
        <ChargeRow label="Unloading" c={unloading} set={setUnloading} />
      </div>

      {banner && <div className={"bs-banner " + (banner.ok ? "ok" : "err")}>{banner.msg}</div>}

      {/* Pinned totals bar */}
      <div className="bs-bar">
        <Stat c="Purchase bill" v={money(t.purchase)} />
        <Stat c="Sale bill" v={money(t.sale)} />
        <Stat c="Freight" v={money(t.freightTotal)} muted />
        <Stat c="Supplier net" v={money(t.supplierNet)} muted />
        <Stat c="Factory net" v={money(t.factoryNet)} muted />
        <div style={{ flex: 1 }} />
        <div className="bs-stat">
          <span className="c">Profit</span>
          <span className="v" style={{ color: t.profit >= 0 ? "#34d399" : "#fb7185", fontSize: 20 }}>{money(t.profit)}</span>
        </div>
        <button className="bs-save" onClick={save} disabled={saving}>
          <Icon name="file-check" size={17} /> {saving ? "Saving…" : "Save trade"}
        </button>
      </div>

      {kg && <KgModal onClose={() => setKg(null)} onApply={applyKg} />}
    </div>
  );
}

function Field({ label, children, badge }: { label: string; children: ReactNode; badge?: ReactNode }) {
  return <label className="fld"><span>{label}</span>{children}{badge}</label>;
}
function Stat({ c, v, muted }: { c: string; v: string; muted?: boolean }) {
  return <div className={"bs-stat" + (muted ? " muted" : "")}><span className="c">{c}</span><span className="v">{v}</span></div>;
}
function balanceBadge(list: Party[], id: string, isSupplier: boolean): ReactNode {
  if (!id) return null;
  const p = list.find((x) => x.id === Number(id));
  if (!p) return null;
  const disp = isSupplier ? -p.balance : p.balance;
  if (disp === 0) return <span className="bal-badge bal-zero">Settled</span>;
  return <span className={"bal-badge " + (disp > 0 ? "bal-pos" : "bal-neg")}>{money(disp)}</span>;
}

function ChargeRow({ label, c, set }: { label: string; c: Charge; set: (c: Charge) => void }) {
  return (
    <div className="chg-row">
      <span className="cap">{label}</span>
      <input className="input" style={{ width: 140 }} inputMode="decimal" value={c.amount} onChange={(e) => set({ ...c, amount: e.target.value })} />
      <span className="lbl-muted">Paid by</span>
      <select className="input" style={{ width: 120 }} value={c.payer} onChange={(e) => set({ ...c, payer: e.target.value as Payer })}>
        {PAYERS.map((p) => <option key={p.v} value={p.v}>{p.label}</option>)}
      </select>
      <button className={"btn-ghost" + (c.splitOn ? " split-on" : "")} onClick={() => set({ ...c, splitOn: !c.splitOn })}>Split</button>
      {c.splitOn && (
        <>
          <span className="lbl-muted">First</span>
          <input className="input" style={{ width: 110 }} inputMode="decimal" value={c.split} onChange={(e) => set({ ...c, split: e.target.value })} />
          <span className="lbl-muted">rest by</span>
          <select className="input" style={{ width: 120 }} value={c.payer2} onChange={(e) => set({ ...c, payer2: e.target.value as Payer })}>
            {PAYERS.map((p) => <option key={p.v} value={p.v}>{p.label}</option>)}
          </select>
        </>
      )}
    </div>
  );
}

function KgModal({ onClose, onApply }: { onClose: () => void; onApply: (mode: "weight" | "rate", v: number) => void }) {
  const [mode, setMode] = useState<"weight" | "rate">("weight");
  const [val, setVal] = useState("");
  const num = parseFloat(val) || 0;
  const preview = mode === "weight" ? num / 40 : num * 40;
  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" style={{ maxWidth: 420 }}>
        <div className="dlg-head"><span className="dlg-chip"><Icon name="receipt" size={21} /></span><span className="dlg-title">Kg calculator</span></div>
        <div className="modal-body">
          <div className="seg" style={{ display: "flex", gap: 6, marginBottom: 14 }}>
            <button className={"btn-ghost" + (mode === "weight" ? " split-on" : "")} style={{ flex: 1 }} onClick={() => setMode("weight")}>Weight</button>
            <button className={"btn-ghost" + (mode === "rate" ? " split-on" : "")} style={{ flex: 1 }} onClick={() => setMode("rate")}>Rate</button>
          </div>
          <label className="fld"><span>{mode === "weight" ? "Weight in kg" : "Rate per kg"}</span>
            <input className="input" autoFocus inputMode="decimal" value={val} onChange={(e) => setVal(e.target.value)} />
          </label>
          <p className="set-note" style={{ marginTop: 10 }}>
            {mode === "weight" ? `= ${money(preview)} maunds  (kg ÷ 40)` : `= ${money(preview)} per maund  (rate/kg × 40)`}
          </p>
        </div>
        <div className="modal-foot">
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn" onClick={() => onApply(mode, num)}>Apply</button>
        </div>
      </div>
    </div>
  );
}
