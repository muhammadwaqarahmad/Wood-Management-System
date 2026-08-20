"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import { Icon } from "@/components/Icon";

/* Mirrors the desktop AuditLogScreen (timber/ui/screens/audit_log_screen.py):
   a "Back to Settings" toolbar, then a table of Time / User / Action / Entity /
   ID / Details. No sidebar entry — reached from the Settings page. */

type Row = {
  when: string; username: string; action: string;
  entity: string; entity_id: number | null; details: string | null;
};

function fmt(iso: string): string {
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function AuditPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try { setRows(await api.get<Row[]>("/audit?limit=500")); }
    catch (e) {
      setError(e instanceof ApiError && e.status === 403
        ? "You don't have permission to view the audit log."
        : e instanceof ApiError ? e.message : "Couldn't reach the API.");
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div>
      <div className="md-toolbar">
        <button className="btn-ghost" onClick={() => router.push("/settings")}>
          <Icon name="chevron-left" size={15} /> Back to Settings
        </button>
        <div className="grow" />
      </div>

      {error ? (
        <div className="card notice" style={{ marginTop: 12 }}><strong>Couldn&apos;t load.</strong><p className="set-note">{error}</p></div>
      ) : !rows ? (
        <p className="muted" style={{ marginTop: 12 }}>Loading…</p>
      ) : (
        <div className="md-card">
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Time</th><th>User</th><th>Action</th><th>Entity</th><th>ID</th><th>Details</th></tr></thead>
              <tbody>
                {rows.length === 0 && <tr><td colSpan={6} className="empty">No records.</td></tr>}
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>{fmt(r.when)}</td>
                    <td>{r.username}</td>
                    <td>{r.action}</td>
                    <td>{r.entity}</td>
                    <td>{r.entity_id ?? ""}</td>
                    <td>{r.details || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
