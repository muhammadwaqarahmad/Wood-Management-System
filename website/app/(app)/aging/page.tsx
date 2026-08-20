"use client";

import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { money } from "@/lib/format";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop AgingScreen (timber/ui/screens/aging_screen.py):
   factory receivables split into 0-30 / 31-60 / 61-90 / 90+ day buckets —
   five bucket tiles (green when young, redder as it ages) and a table. */

type Row = { name: string; b0_30: number; b31_60: number; b61_90: number; b90p: number; total: number };
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

export default function AgingPage() {
  const toast = useToast();
  const [rows, setRows] = useState<Row[]>([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    (async () => {
      try { const d = await api.get<{ rows: Row[] }>("/reports/aging"); setRows(d.rows); }
      catch (e) { toast.error(errMsg(e, "Couldn't reach the API.")); }
    })();
  }, [toast]);

  const sums = useMemo(() => rows.reduce(
    (a, r) => ({ b0_30: a.b0_30 + r.b0_30, b31_60: a.b31_60 + r.b31_60, b61_90: a.b61_90 + r.b61_90, b90p: a.b90p + r.b90p, total: a.total + r.total }),
    { b0_30: 0, b31_60: 0, b61_90: 0, b90p: 0, total: 0 },
  ), [rows]);

  const shown = q ? rows.filter((r) => r.name.toLowerCase().includes(q.toLowerCase())) : rows;

  return (
    <div>
      <div className="tiles" style={{ marginBottom: 12 }}>
        <Tile label="0–30 days" value={money(sums.b0_30)} color="#10b981" icon="calendar-clock" />
        <Tile label="31–60 days" value={money(sums.b31_60)} color="#0ea5e9" icon="calendar-clock" />
        <Tile label="61–90 days" value={money(sums.b61_90)} color="#f59e0b" icon="alarm-clock" />
        <Tile label="90+ days" value={money(sums.b90p)} color="#f43f5e" icon="alert-triangle" />
        <Tile label="Total receivable" value={money(sums.total)} color="#6366f1" icon="wallet" />
      </div>

      <div className="md-bar">
        <div className="search-wrap"><Icon name="search" size={16} /><input className="input" placeholder="Search factories" value={q} onChange={(e) => setQ(e.target.value)} /></div>
      </div>

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th style={{ textAlign: "left" }}>Factory</th>
            <th className="right">0–30 days</th>
            <th className="right">31–60 days</th>
            <th className="right">61–90 days</th>
            <th className="right">90+ days</th>
            <th className="right">Outstanding</th>
          </tr></thead>
          <tbody>
            {shown.length === 0 && <tr><td colSpan={6} className="empty">No receivables.</td></tr>}
            {shown.map((r, i) => (
              <tr key={i}>
                <td>{r.name}</td>
                <td className="right">{r.b0_30 ? money(r.b0_30) : "—"}</td>
                <td className="right">{r.b31_60 ? money(r.b31_60) : "—"}</td>
                <td className="right" style={{ color: r.b61_90 ? "#b45309" : undefined }}>{r.b61_90 ? money(r.b61_90) : "—"}</td>
                <td className="right" style={{ color: r.b90p ? "var(--neg)" : undefined }}>{r.b90p ? money(r.b90p) : "—"}</td>
                <td className="right" style={{ fontWeight: 600 }}>{money(r.total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
