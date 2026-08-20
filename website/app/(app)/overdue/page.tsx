"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop OverdueScreen (timber/ui/screens/overdue_screen.py):
   factories holding our money past their credit period — three tiles
   (Outstanding total / Factory count / worst Days overdue) and a table,
   worst overdue first. No export (the desktop screen has none). */

type Row = {
  name: string; outstanding: number; oldest_date: string;
  days_outstanding: number; credit_days: number; days_overdue: number;
};
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);

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

export default function OverduePage() {
  const toast = useToast();
  const [rows, setRows] = useState<Row[]>([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    (async () => {
      try { const d = await api.get<{ factories: Row[] }>("/reports/overdue"); setRows(d.factories); }
      catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
    })();
  }, [toast]);

  const { total, worst } = useMemo(() => ({
    total: rows.reduce((s, r) => s + r.outstanding, 0),
    worst: rows.reduce((m, r) => Math.max(m, r.days_overdue), 0),
  }), [rows]);

  const shown = q ? rows.filter((r) => r.name.toLowerCase().includes(q.toLowerCase())) : rows;

  return (
    <div>
      <div className="tiles" style={{ marginBottom: 12 }}>
        <Tile label="Outstanding" value={money(total)} color="#f43f5e" icon="alert-triangle" />
        <Tile label="Factory" value={String(rows.length)} color="#6366f1" icon="factory" />
        <Tile label="Days overdue" value={String(worst)} color="#f59e0b" icon="alarm-clock" />
      </div>

      <div className="md-bar">
        <div className="search-wrap"><Icon name="search" size={16} /><input className="input" placeholder="Search factories" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th style={{ textAlign: "left" }}>Factory</th>
            <th className="right">Outstanding</th>
            <th>Oldest unpaid</th>
            <th className="right">Days outstanding</th>
            <th className="right">Credit days</th>
            <th className="right">Days overdue</th>
          </tr></thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={6} className="empty">No overdue factories.</td></tr>}
            {shown.map((r, i) => (
              <tr key={i}>
                <td>{r.name}</td>
                <td className="right">{money(r.outstanding)}</td>
                <td style={{ textAlign: "center" }}>{r.oldest_date}</td>
                <td className="right">{r.days_outstanding}</td>
                <td className="right">{r.credit_days}</td>
                <td className="right" style={{ background: "color-mix(in srgb, var(--neg) 14%, transparent)", color: "var(--neg)", fontWeight: 600 }}>{r.days_overdue}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
