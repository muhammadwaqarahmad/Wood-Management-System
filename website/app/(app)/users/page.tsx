"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Icon } from "@/components/Icon";

type UserRow = { id: number; username: string; full_name: string; role: string; is_active: boolean };
const ROLES = ["Admin", "Manager", "Data Entry", "Accountant", "Viewer"];

export default function UsersPage() {
  const [rows, setRows] = useState<UserRow[]>([]);
  const [form, setForm] = useState({ username: "", password: "", full_name: "", role: "Viewer" });
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try { setRows(await api.get<UserRow[]>("/users")); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Couldn't reach the API (admin only)."); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function create() {
    setError(""); setOk("");
    if (!form.username.trim() || !form.password) return setError("Username and password are required.");
    setBusy(true);
    try {
      await api.post("/users", form);
      setOk("User created.");
      setForm({ username: "", password: "", full_name: "", role: "Viewer" });
      await load();
    } catch (err) { setError(err instanceof ApiError ? err.message : "Could not create."); }
    finally { setBusy(false); }
  }
  async function changeRole(u: UserRow, role: string) {
    try { await api.put(`/users/${u.id}`, { role }); await load(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Failed."); }
  }
  async function toggleActive(u: UserRow) {
    try { await api.put(`/users/${u.id}`, { is_active: !u.is_active }); await load(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Failed."); }
  }
  async function resetPw(u: UserRow) {
    const p = prompt(`New password for ${u.username}:`);
    if (!p) return;
    try { await api.post(`/users/${u.id}/password`, { password: p }); setOk("Password reset."); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Failed."); }
  }
  async function remove(u: UserRow) {
    if (!confirm(`Delete user ${u.username}?`)) return;
    try { await api.del(`/users/${u.id}`); await load(); }
    catch (err) { setError(err instanceof ApiError ? err.message : "Could not delete."); }
  }

  return (
    <div>

      <div className="card">
        <div className="card-head"><span className="chip"><Icon name="plus" size={15} /></span><span className="h">Add user</span></div>
        <div className="form-grid">
          <label className="lbl"><span>Username</span><input className="input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></label>
          <label className="lbl"><span>Full name</span><input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label>
          <label className="lbl"><span>Password</span><input className="input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
          <label className="lbl"><span>Role</span>
            <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select></label>
        </div>
        {error && <div className="login-error" style={{ marginTop: 12 }}>{error}</div>}
        {ok && <div className="banner-ok">{ok}</div>}
        <button className="btn" style={{ marginTop: 12 }} onClick={create} disabled={busy}>{busy ? "Saving…" : "Add user"}</button>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head"><span className="chip"><Icon name="user" size={15} /></span><span className="h">Users</span></div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>Username</th><th>Name</th><th>Role</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={5} className="empty">No users.</td></tr>}
              {rows.map((u) => (
                <tr key={u.id}>
                  <td>{u.username}</td>
                  <td>{u.full_name}</td>
                  <td>
                    <select className="input" style={{ maxWidth: 150 }} value={u.role} onChange={(e) => changeRole(u, e.target.value)}>
                      {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </td>
                  <td>{u.is_active ? "Active" : "Inactive"}</td>
                  <td className="right">
                    <span style={{ display: "inline-flex", gap: 6 }}>
                      <button className="btn-ghost" onClick={() => toggleActive(u)}>{u.is_active ? "Deactivate" : "Activate"}</button>
                      <button className="btn-ghost" onClick={() => resetPw(u)}>Reset PW</button>
                      <button className="btn-danger" onClick={() => remove(u)}>Delete</button>
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
