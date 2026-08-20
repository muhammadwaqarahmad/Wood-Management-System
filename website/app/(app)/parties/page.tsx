"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";

type Party = { id: number; name: string; balance: number };
type Kind = "supplier" | "factory";

export default function PartiesPage() {
  const [kind, setKind] = useState<Kind>("supplier");
  const [rows, setRows] = useState<Party[]>([]);
  const [form, setForm] = useState({ name_en: "", email: "", address: "", credit_days: "" });
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try { setRows(await api.get<Party[]>(`/parties?kind=${kind}`)); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't reach the API."); }
  }, [kind]);
  useEffect(() => { load(); }, [load]);

  async function save() {
    setError(""); setOk("");
    if (!form.name_en.trim()) return setError("Name is required.");
    setBusy(true);
    try {
      await api.post("/parties", {
        party_type: kind, name_en: form.name_en, email: form.email || null,
        address: form.address || null,
        credit_days: form.credit_days ? Number(form.credit_days) : null,
      });
      setOk("Saved.");
      setForm({ name_en: "", email: "", address: "", credit_days: "" });
      await load();
    } catch (err) { setError(err instanceof ApiError ? err.message : "Could not save."); }
    finally { setBusy(false); }
  }

  async function deactivate(id: number) {
    if (!confirm("Deactivate this party?")) return;
    try { await api.post(`/parties/${id}/active?active=false`); await load(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Failed."); }
  }
  async function remove(id: number) {
    if (!confirm("Delete this party? (Only possible if it has no records.)")) return;
    try { await api.del(`/parties/${id}`); await load(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Could not delete."); }
  }

  return (
    <div>

      <div className="toolbar">
        <div className="seg">
          <button className={kind === "supplier" ? "on" : ""} onClick={() => setKind("supplier")}>Suppliers</button>
          <button className={kind === "factory" ? "on" : ""} onClick={() => setKind("factory")}>Factories</button>
        </div>
      </div>

      <div className="card">
        <div className="card-head"><span className="chip"><Icon name="plus" size={15} /></span><span className="h">Add {kind}</span></div>
        <div className="form-grid">
          <label className="lbl"><span>Name</span><input className="input" value={form.name_en} onChange={(e) => setForm({ ...form, name_en: e.target.value })} /></label>
          <label className="lbl"><span>Phone / email</span><input className="input" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label className="lbl"><span>Address</span><input className="input" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></label>
          {kind === "factory" && (
            <label className="lbl"><span>Credit days</span><input className="input right" type="number" value={form.credit_days} onChange={(e) => setForm({ ...form, credit_days: e.target.value })} /></label>
          )}
        </div>
        {error && <div className="login-error" style={{ marginTop: 12 }}>{error}</div>}
        {ok && <div className="banner-ok">{ok}</div>}
        <button className="btn" style={{ marginTop: 12 }} onClick={save} disabled={busy}>{busy ? "Saving…" : "Add"}</button>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><span className="chip"><Icon name="book-user" size={15} /></span><span className="h">{kind === "supplier" ? "Suppliers" : "Factories"}</span></div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Name</th><th className="right">Balance</th><th></th></tr></thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={3} className="empty">None yet.</td></tr>}
              {rows.map((p) => (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  <td className="right" style={{ color: p.balance >= 0 ? "var(--pos)" : "var(--neg)" }}>{money(p.balance)}</td>
                  <td className="right">
                    <span style={{ display: "inline-flex", gap: 6 }}>
                      <button className="btn-ghost" onClick={() => deactivate(p.id)}>Deactivate</button>
                      <button className="btn-danger" onClick={() => remove(p.id)}>Delete</button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
