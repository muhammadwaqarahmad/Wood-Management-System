"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";

/* ---------------------------------------------------------------- tabs ----- */
type TabKey = "users" | "factory" | "supplier" | "wood";
const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: "users", label: "Users", icon: "user" },
  { key: "factory", label: "Factory", icon: "factory" },
  { key: "supplier", label: "Supplier", icon: "book-user" },
  { key: "wood", label: "Wood types", icon: "database" },
];

export default function MasterPage() {
  const [tab, setTab] = useState<TabKey>("users");
  return (
    <div>
      <div className="md-tabs">
        {TABS.map((t) => (
          <button key={t.key} className={"md-tab" + (tab === t.key ? " on" : "")} onClick={() => setTab(t.key)}>
            <Icon name={t.icon} size={16} /> {t.label}
          </button>
        ))}
      </div>
      <div className="md-card">
        {tab === "users" && <UsersPanel />}
        {tab === "factory" && <PartyPanel kind="factory" />}
        {tab === "supplier" && <PartyPanel kind="supplier" />}
        {tab === "wood" && <WoodPanel />}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------ Manage menu -- */
type Action = { label: string; icon: string; run: () => void; danger?: boolean };
function ManageMenu({ actions, up }: { actions: (Action | "sep")[]; up?: boolean }) {
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
        <div className={"manage-menu" + (up ? " up" : "")}>
          {actions.map((a, i) =>
            a === "sep" ? (
              <div className="manage-sep" key={"s" + i} />
            ) : (
              <button key={a.label} className={"manage-item" + (a.danger ? " danger" : "")}
                onClick={() => { setOpen(false); a.run(); }}>
                <Icon name={a.icon} size={16} /> {a.label}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- Modal ---- */
function Modal({ title, icon, wide, onClose, children, onSave, saveLabel = "Save", busy }: {
  title: string; icon: string; wide?: boolean; onClose: () => void; children: ReactNode;
  onSave?: () => void; saveLabel?: string; busy?: boolean;
}) {
  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={"modal" + (wide ? " wide" : "")}>
        <div className="dlg-head">
          <span className="dlg-chip"><Icon name={icon} size={21} /></span>
          <span className="dlg-title">{title}</span>
        </div>
        <div className="modal-body">{children}</div>
        <div className="modal-foot">
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
          {onSave && <button className="btn" onClick={onSave} disabled={busy}>{busy ? "Saving…" : saveLabel}</button>}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="fld"><span>{label}</span>{children}</label>;
}
function errMsg(e: unknown, fallback: string) { return e instanceof ApiError ? e.message : fallback; }

/* ================================================================ Users ==== */
type User = { id: number; username: string; full_name: string; role: string; is_active: boolean };
const ROLES = ["Admin", "Manager", "Viewer"];

function UsersPanel() {
  const toast = useToast();
  const [rows, setRows] = useState<User[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [dialog, setDialog] = useState<null | "add" | "edit">(null);
  const [form, setForm] = useState({ username: "", full_name: "", role: "Viewer", password: "" });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setRows(await api.get<User[]>("/users")); }
    catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  const current = rows.find((r) => r.id === sel) || null;
  function requireSel(): User | null { if (!current) { toast.warning("Select a user first."); return null; } return current; }

  async function save() {
    setBusy(true);
    try {
      if (dialog === "add") {
        await api.post("/users", { username: form.username, full_name: form.full_name, role: form.role, password: form.password });
      } else if (current) {
        await api.put(`/users/${current.id}`, { full_name: form.full_name, role: form.role });
      }
      setDialog(null); toast.success("Saved."); await load();
    } catch (e) { toast.error(errMsg(e, "Could not save.")); }
    finally { setBusy(false); }
  }
  async function resetPw() {
    const u = requireSel(); if (!u) return;
    const pw = prompt(`New password for ${u.username}:`);
    if (!pw) return;
    try { await api.post(`/users/${u.id}/password`, { password: pw }); toast.success("Password reset."); }
    catch (e) { toast.error(errMsg(e, "Failed.")); }
  }
  async function toggle() {
    const u = requireSel(); if (!u) return;
    try { await api.put(`/users/${u.id}`, { is_active: !u.is_active }); toast.success("Saved."); await load(); }
    catch (e) { toast.error(errMsg(e, "Failed.")); }
  }
  async function del() {
    const u = requireSel(); if (!u) return;
    if (!(await toast.confirm({ title: "Delete", text: `Delete user "${u.username}"?`, danger: true }))) return;
    try { await api.del(`/users/${u.id}`); setSel(null); toast.success("Deleted."); await load(); }
    catch (e) { toast.error(errMsg(e, "Could not delete.")); }
  }

  return (
    <div>
      <div className="md-toolbar top">
        <div className="grow" />
        <ManageMenu actions={[
          { label: "Add", icon: "plus", run: () => { setForm({ username: "", full_name: "", role: "Viewer", password: "" }); setDialog("add"); } },
          { label: "Edit", icon: "pencil", run: () => { const u = requireSel(); if (u) { setForm({ username: u.username, full_name: u.full_name, role: u.role, password: "" }); setDialog("edit"); } } },
          { label: "Reset password", icon: "key", run: resetPw },
          { label: current?.is_active === false ? "Activate" : "Deactivate", icon: "lock", run: toggle },
          "sep",
          { label: "Delete", icon: "trash", run: del, danger: true },
        ]} />
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>Username</th><th>Full name</th><th>Role</th><th>Status</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={4} className="empty">No users.</td></tr>}
            {rows.map((u) => (
              <tr key={u.id} onClick={() => setSel(u.id)} style={{ cursor: "pointer", ...(sel === u.id ? { background: "var(--sel-row)" } : {}) }}>
                <td>{u.username}</td><td>{u.full_name || "—"}</td><td>{u.role}</td>
                <td>{u.is_active ? "Active" : "Inactive"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {dialog && (
        <Modal title={dialog === "add" ? "Add user" : "Edit user"} icon="user" onClose={() => setDialog(null)} onSave={save} busy={busy}>
          <Field label="Username">
            <input className="input" value={form.username} disabled={dialog === "edit"} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </Field>
          <Field label="Full name">
            <input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
          </Field>
          <Field label="Role">
            <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </Field>
          {dialog === "add" && (
            <Field label="Password">
              <input className="input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </Field>
          )}
        </Modal>
      )}
    </div>
  );
}

/* ============================================================= Wood types == */
type Wood = { id: number; name: string; default_supplier_rate: number; default_factory_rate: number; is_active: boolean };

function WoodPanel() {
  const toast = useToast();
  const [rows, setRows] = useState<Wood[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [rates, setRates] = useState<null | { sup: string; fac: string }>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { const d = await api.get<{ wood_types: Wood[] }>("/master/wood-types"); setRows(d.wood_types); }
    catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
  }, [toast]);
  useEffect(() => { load(); }, [load]);

  const current = rows.find((r) => r.id === sel) || null;
  function requireSel(): Wood | null { if (!current) { toast.warning("Select a wood type first."); return null; } return current; }

  async function add() {
    const n = prompt("Wood type name:"); if (!n || !n.trim()) return;
    try { await api.post("/master/wood_type", { name: n.trim() }); toast.success("Added."); await load(); }
    catch (e) { toast.error(errMsg(e, "Failed.")); }
  }
  async function rename() {
    const w = requireSel(); if (!w) return;
    const n = prompt("New name:", w.name); if (!n || !n.trim()) return;
    try { await api.put(`/master/wood_type/${w.id}`, { name: n.trim() }); toast.success("Saved."); await load(); }
    catch (e) { toast.error(errMsg(e, "Failed.")); }
  }
  async function saveRates() {
    const w = current; if (!w || !rates) return;
    setBusy(true);
    try {
      await api.post(`/master/wood_type/${w.id}/rates`, { supplier_rate: Number(rates.sup) || 0, factory_rate: Number(rates.fac) || 0 });
      setRates(null); toast.success("Saved."); await load();
    } catch (e) { toast.error(errMsg(e, "Failed.")); }
    finally { setBusy(false); }
  }
  async function toggle() {
    const w = requireSel(); if (!w) return;
    try { await api.post(`/master/wood_type/${w.id}/active?active=${!w.is_active}`); toast.success("Saved."); await load(); }
    catch (e) { toast.error(errMsg(e, "Failed.")); }
  }
  async function del() {
    const w = requireSel(); if (!w) return;
    if (!(await toast.confirm({ title: "Delete", text: `Delete "${w.name}"?`, danger: true }))) return;
    try { await api.del(`/master/wood_type/${w.id}`); setSel(null); toast.success("Deleted."); await load(); }
    catch (e) { toast.error(errMsg(e, "Could not delete.")); }
  }

  return (
    <div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>Name</th><th className="right">Supplier rate</th><th className="right">Factory rate</th><th>Status</th></tr></thead>
          <tbody>
            {rows.length === 0 && <tr><td colSpan={4} className="empty">No wood types.</td></tr>}
            {rows.map((w) => (
              <tr key={w.id} onClick={() => setSel(w.id)} style={{ cursor: "pointer", ...(sel === w.id ? { background: "var(--sel-row)" } : {}) }}>
                <td>{w.name}</td>
                <td className="right">{w.default_supplier_rate ? money(w.default_supplier_rate) : "—"}</td>
                <td className="right">{w.default_factory_rate ? money(w.default_factory_rate) : "—"}</td>
                <td>{w.is_active ? "Active" : "Inactive"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="md-toolbar bottom">
        <ManageMenu up actions={[
          { label: "Add", icon: "plus", run: add },
          { label: "Rename", icon: "pencil", run: rename },
          { label: "Set rates", icon: "trending-up", run: () => { const w = requireSel(); if (w) setRates({ sup: String(w.default_supplier_rate || ""), fac: String(w.default_factory_rate || "") }); } },
          { label: current?.is_active === false ? "Activate" : "Deactivate", icon: "eye-off", run: toggle },
          "sep",
          { label: "Delete", icon: "trash", run: del, danger: true },
        ]} />
        <div className="grow" />
      </div>

      {rates && (
        <Modal title={`Set rates — ${current?.name ?? ""}`} icon="trending-up" onClose={() => setRates(null)} onSave={saveRates} busy={busy}>
          <Field label="Supplier rate (buy)"><input className="input" inputMode="decimal" value={rates.sup} onChange={(e) => setRates({ ...rates, sup: e.target.value })} /></Field>
          <Field label="Factory rate (sell)"><input className="input" inputMode="decimal" value={rates.fac} onChange={(e) => setRates({ ...rates, fac: e.target.value })} /></Field>
        </Modal>
      )}
    </div>
  );
}

/* ========================================================= Factory/Supplier = */
type Party = {
  id: number; name: string; balance: number;
  phones?: string[]; location?: string | null; address?: string | null; banks?: string[];
  is_active?: boolean; overdue?: boolean;
};
type Loc = { id: number; name: string };
type Bank = { account_title: string; bank_name: string; iban: string; account_number: string };
const BLANK = { name_en: "", name_ur: "", email: "", address: "", location_id: "", opening_balance: "", credit_days: "" };

function PartyPanel({ kind }: { kind: "factory" | "supplier" }) {
  const toast = useToast();
  const [rows, setRows] = useState<Party[]>([]);
  const [locs, setLocs] = useState<Loc[]>([]);
  const [sel, setSel] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"all" | "active" | "inactive">("all");
  const [dialog, setDialog] = useState<null | "add" | number>(null);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ ...BLANK });
  const [phones, setPhones] = useState<string[]>([]);
  const [phone, setPhone] = useState("");
  const [banks, setBanks] = useState<Bank[]>([]);
  const isSupplier = kind === "supplier";

  const load = useCallback(async () => {
    try {
      const [ps, ld] = await Promise.all([
        api.get<Party[]>(`/parties?kind=${kind}`),
        api.get<{ locations: Loc[] }>("/master/locations").catch(() => ({ locations: [] })),
      ]);
      setRows(ps); setLocs(ld.locations);
    } catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
  }, [kind, toast]);
  useEffect(() => { load(); }, [load]);

  const current = rows.find((r) => r.id === sel) || null;
  function requireSel(): Party | null { if (!current) { toast.warning("Select a row first."); return null; } return current; }

  const shown = rows.filter((r) => {
    if (q && !r.name.toLowerCase().includes(q.toLowerCase())) return false;
    if (status !== "all" && r.is_active !== undefined && r.is_active !== (status === "active")) return false;
    return true;
  });

  function openAdd() { setF({ ...BLANK }); setPhones([]); setBanks([]); setPhone(""); setDialog("add"); }
  async function openEdit() {
    const p = requireSel(); if (!p) return;
    try {
      const d = await api.get<{
        name_en: string; name_ur: string; email: string; address: string;
        location_id: number | null; opening_balance: number; credit_days: number | null;
        phones: string[]; banks: Bank[];
      }>(`/parties/${p.id}`);
      setF({
        name_en: d.name_en || "", name_ur: d.name_ur || "", email: d.email || "", address: d.address || "",
        location_id: d.location_id ? String(d.location_id) : "", opening_balance: String(d.opening_balance ?? ""),
        credit_days: d.credit_days ? String(d.credit_days) : "",
      });
      setPhones(d.phones || []); setBanks(d.banks || []); setPhone(""); setDialog(p.id);
    } catch (e) { toast.error(errMsg(e, "Could not load.")); }
  }

  async function save() {
    setBusy(true);
    const payload = {
      name_en: f.name_en, name_ur: f.name_ur, email: f.email, address: f.address,
      location_id: f.location_id ? Number(f.location_id) : null,
      opening_balance: Number(f.opening_balance) || 0,
      credit_days: kind === "factory" && f.credit_days ? Number(f.credit_days) : null,
      phones, banks,
    };
    try {
      if (dialog === "add") await api.post("/parties", { party_type: kind, ...payload });
      else await api.put(`/parties/${dialog}`, payload);
      setDialog(null); toast.success("Saved."); await load();
    } catch (e) { toast.error(errMsg(e, "Could not save.")); }
    finally { setBusy(false); }
  }
  async function toggle() {
    const p = requireSel(); if (!p) return;
    try { await api.post(`/parties/${p.id}/active?active=${!(p.is_active ?? true)}`); toast.success("Saved."); await load(); }
    catch (e) { toast.error(errMsg(e, "Failed.")); }
  }
  async function del() {
    const p = requireSel(); if (!p) return;
    if (!(await toast.confirm({ title: "Delete", text: `Delete "${p.name}"?`, danger: true }))) return;
    try { await api.del(`/parties/${p.id}`); setSel(null); toast.success("Deleted."); await load(); }
    catch (e) { toast.error(errMsg(e, "Could not delete.")); }
  }
  const setBank = (i: number, k: keyof Bank, v: string) => setBanks(banks.map((b, j) => (j === i ? { ...b, [k]: v } : b)));

  return (
    <div>
      <div className="md-filters">
        <div className="search-wrap">
          <Icon name="search" size={16} />
          <input className="input" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value as typeof status)} style={{ maxWidth: 140 }}>
          <option value="all">All</option><option value="active">Active</option><option value="inactive">Inactive</option>
        </select>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th>Name</th><th>Phone</th><th>Location</th><th>Address</th><th>Banks</th>
            <th className="right">Balance</th><th>Status</th>
          </tr></thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={7} className="empty">No {isSupplier ? "suppliers" : "factories"}.</td></tr>}
            {shown.map((p) => {
              const disp = isSupplier ? -p.balance : p.balance;
              return (
                <tr key={p.id} onClick={() => setSel(p.id)}
                  style={{ cursor: "pointer", ...(sel === p.id ? { background: "var(--sel-row)" } : (p.overdue ? { background: "color-mix(in srgb, var(--neg) 12%, transparent)" } : {})) }}>
                  <td>{p.name}</td>
                  <td>{p.phones?.length ? p.phones.join(", ") : "—"}</td>
                  <td>{p.location || "—"}</td>
                  <td>{p.address || "—"}</td>
                  <td>{p.banks?.length ? p.banks.join(" | ") : "—"}</td>
                  <td className="right" style={{ color: disp < 0 ? "var(--neg)" : disp > 0 ? "var(--pos)" : "var(--text)" }}>{money(disp)}</td>
                  <td>{p.overdue ? "Overdue" : p.is_active === false ? "Inactive" : "Active"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="md-toolbar bottom">
        <ManageMenu up actions={[
          { label: "Add", icon: "plus", run: openAdd },
          { label: "Edit", icon: "pencil", run: openEdit },
          { label: current?.is_active === false ? "Activate" : "Deactivate", icon: "eye-off", run: toggle },
          "sep",
          { label: "Delete", icon: "trash", run: del, danger: true },
        ]} />
        <div className="grow" />
      </div>

      {dialog !== null && (
        <Modal title={(dialog === "add" ? "Add " : "Edit ") + (isSupplier ? "supplier" : "factory")}
          icon={isSupplier ? "book-user" : "factory"} wide onClose={() => setDialog(null)} onSave={save} busy={busy}>
          <div className="grid2">
            <Field label="Name (English)"><input className="input" value={f.name_en} onChange={(e) => setF({ ...f, name_en: e.target.value })} /></Field>
            <Field label="Name (اردو)"><input className="input" value={f.name_ur} onChange={(e) => setF({ ...f, name_ur: e.target.value })} /></Field>
            <Field label="Email"><input className="input" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
            <Field label="Address"><input className="input" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} /></Field>
            <Field label="Location">
              <select className="input" value={f.location_id} onChange={(e) => setF({ ...f, location_id: e.target.value })}>
                <option value="">—</option>
                {locs.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </Field>
            <Field label="Opening balance"><input className="input" inputMode="decimal" value={f.opening_balance} onChange={(e) => setF({ ...f, opening_balance: e.target.value })} /></Field>
            {kind === "factory" && <Field label="Credit days"><input className="input" inputMode="numeric" value={f.credit_days} onChange={(e) => setF({ ...f, credit_days: e.target.value })} /></Field>}
          </div>

          <div className="dlg-lower">
          <Field label="Phones">
            <div style={{ display: "flex", gap: 8 }}>
              <input className="input" value={phone} placeholder="03001234567" maxLength={11}
                onChange={(e) => setPhone(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && phone.trim()) { setPhones([...phones, phone.trim()]); setPhone(""); } }} />
              <button className="btn-ghost" type="button" onClick={() => { if (phone.trim()) { setPhones([...phones, phone.trim()]); setPhone(""); } }}>Add</button>
            </div>
            {phones.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
                {phones.map((p, i) => (
                  <span key={i} style={{ background: "var(--tab-bg)", borderRadius: 8, padding: "3px 8px", fontSize: 12 }}>
                    {p} <button type="button" style={{ border: "none", background: "none", cursor: "pointer", color: "var(--neg)" }} onClick={() => setPhones(phones.filter((_, j) => j !== i))}>×</button>
                  </span>
                ))}
              </div>
            )}
          </Field>

          <Field label="Bank accounts">
            <div style={{ display: "grid", gap: 10 }}>
              {banks.map((b, i) => (
                <div key={i} className="grid2" style={{ alignItems: "end", border: "1px solid var(--border)", borderRadius: 10, padding: 10 }}>
                  <input className="input" placeholder="Account title" value={b.account_title} onChange={(e) => setBank(i, "account_title", e.target.value)} />
                  <input className="input" placeholder="Bank name" value={b.bank_name} onChange={(e) => setBank(i, "bank_name", e.target.value)} />
                  <input className="input" placeholder="IBAN" maxLength={24} value={b.iban} onChange={(e) => setBank(i, "iban", e.target.value)} />
                  <div style={{ display: "flex", gap: 8 }}>
                    <input className="input" placeholder="Account number" value={b.account_number} onChange={(e) => setBank(i, "account_number", e.target.value)} />
                    <button className="btn-danger" type="button" onClick={() => setBanks(banks.filter((_, j) => j !== i))}>×</button>
                  </div>
                </div>
              ))}
              <button className="btn-ghost" type="button" onClick={() => setBanks([...banks, { account_title: "", bank_name: "", iban: "", account_number: "" }])}>Add bank account</button>
            </div>
          </Field>
          </div>
        </Modal>
      )}
    </div>
  );
}
