"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { SearchSelect } from "@/components/SearchSelect";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop TradeHistoryScreen (timber/ui/screens/trade_history_screen.py):
   period + limit filter, KPI tiles (trades / weight / sales / profit) and the
   full trade table, with search and per-row void. */

type Trade = {
  id: number; txn_date: string; vehicle: string; wood: string;
  bapari_name: string; bapari_rate: number; factory_name: string; factory_rate: number;
  muds: number; kg: number; purchase_bill: number; sale_bill: number; profit: number;
  lines: number; loading: number; freight: number; unloading: number;
};
type Data = { total_count: number; totals: [number, number, number]; trades: Trade[] };

const TONES: Record<string, string> = { accent: "#6366f1", slate: "#64748b", sky: "#0ea5e9", emerald: "#10b981" };
const PERIODS = [
  { key: "all", label: "All time" }, { key: "day", label: "Today" }, { key: "week", label: "This week" },
  { key: "month", label: "This month" }, { key: "year", label: "This year" }, { key: "custom", label: "Custom" },
];
const LIMITS = [{ v: "100", label: "100" }, { v: "500", label: "500" }, { v: "1000", label: "All" }];
const iso = (d: Date) => d.toISOString().slice(0, 10);

function range(p: string, from: string, to: string): string {
  const t = new Date();
  if (p === "day") return `&start=${iso(t)}&end=${iso(t)}`;
  if (p === "week") {
    const s = new Date(t); s.setDate(t.getDate() - ((t.getDay() + 6) % 7));
    const e = new Date(s); e.setDate(s.getDate() + 6);
    return `&start=${iso(s)}&end=${iso(e)}`;
  }
  if (p === "month") return `&start=${iso(new Date(t.getFullYear(), t.getMonth(), 1))}&end=${iso(t)}`;
  if (p === "year") return `&start=${iso(new Date(t.getFullYear(), 0, 1))}&end=${iso(t)}`;
  if (p === "custom") return `&start=${from}&end=${to}`;
  return "";
}

function Tile({ label, value, tone, icon, signed }: { label: string; value: string; tone: string; icon: string; signed?: number }) {
  const c = TONES[tone];
  const color = signed === undefined ? "var(--text)" : signed > 0 ? "var(--pos)" : signed < 0 ? "var(--neg)" : "var(--text)";
  return (
    <div className="tile" style={{ borderLeftColor: c }}>
      <div className="cap"><span className="chip" style={{ background: `linear-gradient(135deg, ${c}, color-mix(in srgb, ${c} 60%, #fff))` }}><Icon name={icon} size={16} /></span>{label}</div>
      <div className="val" style={{ color }}>{value}</div>
    </div>
  );
}

export default function TradesPage() {
  const toast = useToast();
  const [period, setPeriod] = useState("day");
  const [from, setFrom] = useState(() => iso(new Date(Date.now() - 30 * 864e5)));
  const [to, setTo] = useState(() => iso(new Date()));
  const [limit, setLimit] = useState("100");
  const [q, setQ] = useState("");
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [editId, setEditId] = useState<number | null>(null);
  const [opts, setOpts] = useState<{ sup: Opt[]; fac: Opt[]; wood: Opt[] }>({ sup: [], fac: [], wood: [] });

  const load = useCallback(async () => {
    setError("");
    try { setData(await api.get<Data>(`/trades?limit=${limit}${range(period, from, to)}`)); }
    catch (e) { setError(e instanceof ApiError ? e.message : "Couldn't reach the API."); }
  }, [period, from, to, limit]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {   // dropdown data for the edit modal
    (async () => {
      try {
        const [s, f, w] = await Promise.all([
          api.get<{ id: number; name: string }[]>("/parties?kind=supplier"),
          api.get<{ id: number; name: string }[]>("/parties?kind=factory"),
          api.get<{ wood_types: { id: number; name: string }[] }>("/master/wood-types"),
        ]);
        setOpts({
          sup: s.map((p) => ({ value: String(p.id), label: p.name })),
          fac: f.map((p) => ({ value: String(p.id), label: p.name })),
          wood: w.wood_types.map((x) => ({ value: String(x.id), label: x.name })),
        });
      } catch { /* edit modal will still open; selects just won't list */ }
    })();
  }, []);

  async function voidTrade(t: Trade) {
    if (!(await toast.confirm({ title: "Delete trade", text: `Cancel the trade (${t.wood}) with ${t.factory_name}? This voids both the purchase and the sale.`, danger: true, okText: "Delete" }))) return;
    try { await api.post(`/trades/${t.id}/void`); toast.success("Trade voided."); await load(); }
    catch (e) { toast.error(e instanceof ApiError ? e.message : "Could not void."); }
  }

  const shown = useMemo(() => {
    if (!data) return [];
    if (!q) return data.trades;
    const s = q.toLowerCase();
    return data.trades.filter((t) =>
      [t.vehicle, t.wood, t.bapari_name, t.factory_name].some((x) => (x || "").toLowerCase().includes(s)));
  }, [data, q]);

  const [profit, sale, muds] = data?.totals ?? [0, 0, 0];

  return (
    <div>
      <div className="toolbar">
        <span style={{ fontWeight: 700, color: "var(--muted)" }}>Period:</span>
        <select className="input" style={{ maxWidth: 150 }} value={period} onChange={(e) => setPeriod(e.target.value)}>
          {PERIODS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
        </select>
        {period === "custom" && (
          <>
            <input className="input" type="date" style={{ maxWidth: 160 }} value={from} onChange={(e) => setFrom(e.target.value)} />
            <input className="input" type="date" style={{ maxWidth: 160 }} value={to} onChange={(e) => setTo(e.target.value)} />
          </>
        )}
        <span style={{ fontWeight: 700, color: "var(--muted)", marginInlineStart: 8 }}>Show:</span>
        <select className="input" style={{ maxWidth: 90 }} value={limit} onChange={(e) => setLimit(e.target.value)}>
          {LIMITS.map((l) => <option key={l.v} value={l.v}>{l.label}</option>)}
        </select>
        <div className="grow" style={{ flex: 1 }} />
        <div className="search-wrap" style={{ maxWidth: 260 }}><Icon name="search" size={16} /><input className="input" placeholder="Search trades" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>

      <div className="tiles" style={{ marginBottom: 16 }}>
        <Tile label="Trades" value={String(data?.total_count ?? 0)} tone="accent" icon="receipt" />
        <Tile label="Total weight" value={`${money(muds)} muds`} tone="slate" icon="database" />
        <Tile label="Total sales" value={money(sale)} tone="sky" icon="wallet" />
        <Tile label="Total profit" value={money(profit)} tone="emerald" icon="trending-up" signed={profit} />
      </div>

      {error && <div className="card notice"><strong>Couldn&apos;t load.</strong><p className="set-note">{error}</p></div>}
      <div className="card">
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr>
              <th>Date</th><th>Vehicle no.</th><th style={{ textAlign: "left" }}>Wood type</th><th className="right">Weight</th>
              <th style={{ textAlign: "left" }}>Supplier</th><th className="right">Buy rate</th>
              <th style={{ textAlign: "left" }}>Factory</th><th className="right">Sell rate</th>
              <th className="right">Purchase bill</th><th className="right">Sale bill</th><th className="right">Freight</th><th className="right">Profit</th><th />
            </tr></thead>
            <tbody>
              {shown.length === 0 && <tr><td colSpan={13} className="empty">No trades for this period.</td></tr>}
              {shown.map((t) => {
                const mixed = t.lines > 1;
                const freight = (t.loading || 0) + (t.freight || 0) + (t.unloading || 0);
                return (
                  <tr key={t.id}>
                    <td>{t.txn_date}</td>
                    <td>{t.vehicle || "—"}</td>
                    <td>{mixed ? `${t.wood} (${t.lines})` : t.wood || "—"}</td>
                    <td className="right">{money(t.muds)}{t.kg ? ` + ${t.kg}kg` : ""}</td>
                    <td>{t.bapari_name}</td>
                    <td className="right">{mixed ? "—" : money(t.bapari_rate)}</td>
                    <td>{t.factory_name}</td>
                    <td className="right">{mixed ? "—" : money(t.factory_rate)}</td>
                    <td className="right">{money(t.purchase_bill)}</td>
                    <td className="right">{money(t.sale_bill)}</td>
                    <td className="right">{freight ? money(freight) : "—"}</td>
                    <td className="right" style={{ color: t.profit >= 0 ? "var(--pos)" : "var(--neg)", fontWeight: 600 }}>{money(t.profit)}</td>
                    <td className="right" style={{ whiteSpace: "nowrap" }}>
                      <button className="btn-ghost" onClick={() => setEditId(t.id)}>Edit</button>{" "}
                      <button className="btn-ghost" onClick={() => voidTrade(t)}>Void</button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {editId != null && (
        <TradeEditModal id={editId} opts={opts} onClose={() => setEditId(null)} onSaved={() => { setEditId(null); load(); }} />
      )}
    </div>
  );
}

/* ---- edit a saved trade (mirrors the desktop TradeEditDialog) ---- */
type Opt = { value: string; label: string };
type EditRow = { key: number; wood: string; facW: string; facR: string; supW: string; supR: string };
type Payer = "us" | "factory" | "bapari";
type EditCharge = { amount: string; payer: Payer; splitOn: boolean; split: string; payer2: Payer };
const PAYERS: { v: Payer; label: string }[] = [{ v: "us", label: "Us" }, { v: "factory", label: "Factory" }, { v: "bapari", label: "Supplier" }];
const nn = (s: string) => parseFloat(s) || 0;

function TradeEditModal({ id, opts, onClose, onSaved }: {
  id: number; opts: { sup: Opt[]; fac: Opt[]; wood: Opt[] }; onClose: () => void; onSaved: () => void;
}) {
  const toast = useToast();
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [date, setDate] = useState(""); const [vehicle, setVehicle] = useState("");
  const [supplierId, setSupplierId] = useState(""); const [factoryId, setFactoryId] = useState("");
  const [rows, setRows] = useState<EditRow[]>([]);
  const [rid, setRid] = useState(1);
  const blankCharge = (): EditCharge => ({ amount: "", payer: "factory", splitOn: false, split: "", payer2: "us" });
  const [loading, setLoading] = useState<EditCharge>(blankCharge());
  const [freight, setFreight] = useState<EditCharge>(blankCharge());
  const [unloading, setUnloading] = useState<EditCharge>(blankCharge());

  useEffect(() => {
    (async () => {
      try {
        const d = await api.get<{
          txn_date: string; vehicle_no: string; bapari_id: number; factory_id: number;
          lines: { wood_type_id: number | null; muds: number; kg: number; bapari_rate: number; factory_rate: number; factory_muds: number; factory_kg: number }[];
          loading_amount: number; loading_payer: Payer; loading_payer2: Payer | null; loading_split: number;
          freight_amount: number; freight_payer: Payer; freight_payer2: Payer | null; freight_split: number;
          unloading_amount: number; unloading_payer: Payer; unloading_payer2: Payer | null; unloading_split: number;
        }>(`/trades/${id}`);
        setDate(d.txn_date); setVehicle(d.vehicle_no || "");
        setSupplierId(String(d.bapari_id)); setFactoryId(String(d.factory_id));
        setRows(d.lines.map((ln, i) => ({
          key: i + 1, wood: ln.wood_type_id ? String(ln.wood_type_id) : "",
          facW: String(ln.factory_muds), facR: String(ln.factory_rate),
          supW: String(ln.muds), supR: String(ln.bapari_rate),
        })));
        setRid(d.lines.length + 1);
        const asCharge = (a: number, p: Payer, p2: Payer | null, sp: number): EditCharge =>
          ({ amount: a ? String(a) : "", payer: p || "factory", splitOn: !!p2 && sp > 0, split: sp ? String(sp) : "", payer2: p2 || "us" });
        setLoading(asCharge(d.loading_amount, d.loading_payer, d.loading_payer2, d.loading_split));
        setFreight(asCharge(d.freight_amount, d.freight_payer, d.freight_payer2, d.freight_split));
        setUnloading(asCharge(d.unloading_amount, d.unloading_payer, d.unloading_payer2, d.unloading_split));
        setLoaded(true);
      } catch (e) { toast.error(e instanceof ApiError ? e.message : "Couldn't load the trade."); onClose(); }
    })();
  }, [id, toast, onClose]);

  function patch(k: number, p: Partial<EditRow>) { setRows((rs) => rs.map((r) => (r.key === k ? { ...r, ...p } : r))); }
  function onFacW(k: number, v: string) { patch(k, { facW: v, supW: String(Math.trunc(nn(v))) }); }
  function chargePayload(c: EditCharge) {
    const amt = nn(c.amount), sp = nn(c.split), split = c.splitOn && sp > 0 && sp < amt;
    return { amount: amt, payer: c.payer, payer2: split ? c.payer2 : null, split: split ? sp : 0 };
  }
  async function save() {
    if (!supplierId || !factoryId) { toast.warning("Select a supplier and a factory."); return; }
    setBusy(true);
    const L = chargePayload(loading), F = chargePayload(freight), U = chargePayload(unloading);
    try {
      await api.put(`/trades/${id}`, {
        txn_date: date, bapari_id: Number(supplierId), factory_id: Number(factoryId),
        vehicle_no: vehicle.trim() || null,
        lines: rows.map((r) => ({ wood_type_id: r.wood ? Number(r.wood) : null, muds: nn(r.supW), kg: 0, bapari_rate: nn(r.supR), factory_rate: nn(r.facR), factory_muds: nn(r.facW), factory_kg: 0 })),
        loading_amount: L.amount, loading_payer: L.payer, loading_payer2: L.payer2, loading_split: L.split,
        freight_amount: F.amount, freight_payer: F.payer, freight_payer2: F.payer2, freight_split: F.split,
        unloading_amount: U.amount, unloading_payer: U.payer, unloading_payer2: U.payer2, unloading_split: U.split,
      });
      toast.success("Trade updated."); onSaved();
    } catch (e) { toast.error(e instanceof ApiError ? e.message : "Could not save."); }
    finally { setBusy(false); }
  }

  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal wide">
        <div className="dlg-head"><span className="dlg-chip"><Icon name="history" size={21} /></span><span className="dlg-title">Edit trade</span></div>
        <div className="modal-body">
          {!loaded ? <p className="muted">Loading…</p> : (
            <>
              <div className="grid2">
                <EField label="Date"><input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></EField>
                <EField label="Vehicle no."><input className="input" value={vehicle} onChange={(e) => setVehicle(e.target.value)} /></EField>
                <EField label="Supplier"><SearchSelect value={supplierId} options={opts.sup} onChange={setSupplierId} /></EField>
                <EField label="Factory"><SearchSelect value={factoryId} options={opts.fac} onChange={setFactoryId} /></EField>
              </div>

              <div className="wood-grid wood-head" style={{ marginTop: 8 }}>
                <span>Wood type</span><span>Factory weight</span><span>Factory rate</span><span>Kg</span><span>Supplier weight</span><span>Supplier rate</span><span />
              </div>
              {rows.map((r) => (
                <div className="wood-grid wood-row" key={r.key}>
                  <SearchSelect value={r.wood} options={opts.wood} onChange={(v) => patch(r.key, { wood: v })} />
                  <input className="input" inputMode="decimal" value={r.facW} onChange={(e) => onFacW(r.key, e.target.value)} />
                  <input className="input" inputMode="decimal" value={r.facR} onChange={(e) => patch(r.key, { facR: e.target.value })} />
                  <span />
                  <input className="input" inputMode="decimal" value={r.supW} onChange={(e) => patch(r.key, { supW: e.target.value })} />
                  <input className="input" inputMode="decimal" value={r.supR} onChange={(e) => patch(r.key, { supR: e.target.value })} />
                  <button className="del-x" onClick={() => setRows((rs) => (rs.length <= 1 ? rs : rs.filter((x) => x.key !== r.key)))} aria-label="Remove"><Icon name="x" size={15} /></button>
                </div>
              ))}
              <div style={{ marginTop: 10 }}>
                <button className="btn-dark" onClick={() => { setRows((rs) => [...rs, { key: rid, wood: "", facW: "", facR: "", supW: "", supR: "" }]); setRid((x) => x + 1); }}><Icon name="plus" size={15} /> Add wood</button>
              </div>

              <div style={{ marginTop: 14 }}>
                <ECharge label="Loading" c={loading} set={setLoading} />
                <ECharge label="Freight" c={freight} set={setFreight} />
                <ECharge label="Unloading" c={unloading} set={setUnloading} />
              </div>
            </>
          )}
        </div>
        <div className="modal-foot">
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn" onClick={save} disabled={busy || !loaded}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </div>
    </div>
  );
}

function EField({ label, children }: { label: string; children: ReactNode }) {
  return <label className="fld"><span>{label}</span>{children}</label>;
}
function ECharge({ label, c, set }: { label: string; c: EditCharge; set: (c: EditCharge) => void }) {
  return (
    <div className="chg-row">
      <span className="cap">{label}</span>
      <input className="input" style={{ width: 130 }} inputMode="decimal" value={c.amount} onChange={(e) => set({ ...c, amount: e.target.value })} />
      <span className="lbl-muted">Paid by</span>
      <select className="input" style={{ width: 110 }} value={c.payer} onChange={(e) => set({ ...c, payer: e.target.value as Payer })}>
        {PAYERS.map((p) => <option key={p.v} value={p.v}>{p.label}</option>)}
      </select>
      <button className={"btn-ghost" + (c.splitOn ? " split-on" : "")} onClick={() => set({ ...c, splitOn: !c.splitOn })}>Split</button>
      {c.splitOn && (
        <>
          <span className="lbl-muted">First</span>
          <input className="input" style={{ width: 100 }} inputMode="decimal" value={c.split} onChange={(e) => set({ ...c, split: e.target.value })} />
          <span className="lbl-muted">rest by</span>
          <select className="input" style={{ width: 110 }} value={c.payer2} onChange={(e) => set({ ...c, payer2: e.target.value as Payer })}>
            {PAYERS.map((p) => <option key={p.v} value={p.v}>{p.label}</option>)}
          </select>
        </>
      )}
    </div>
  );
}
