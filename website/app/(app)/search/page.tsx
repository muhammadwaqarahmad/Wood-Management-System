"use client";

import { useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { Icon } from "@/components/Icon";
import { useToast } from "@/lib/toast";

/* Mirrors the desktop SearchScreen (timber/ui/screens/search_screen.py):
   one search box + Type and Period filters, a results count, and a table
   (Type / Date / Name / Detail / Amount) with the Type tinted by kind.
   The API applies its limit PER kind, so filtering Type in the browser gives
   exactly the same rows as the desktop's server-side kind filter. */

type Result = { kind: string; date: string; name: string; detail: string; amount: string };

const KINDS = [
  { v: "", label: "All" }, { v: "party", label: "Party" }, { v: "purchase", label: "Purchase" },
  { v: "sale", label: "Sale" }, { v: "payment", label: "Payment" },
];
const PERIODS = [
  { v: "all", label: "All" }, { v: "day", label: "Day" }, { v: "week", label: "Week" },
  { v: "month", label: "Month" }, { v: "year", label: "Year" },
];
// One accent per result kind, so the Type column reads at a glance (desktop _KIND_TONE).
const KIND_TONE: Record<string, string> = {
  party: "#6366f1", purchase: "#10b981", sale: "#0ea5e9", payment: "#f59e0b",
};
const KIND_LABEL: Record<string, string> = {
  party: "Party", purchase: "Purchase", sale: "Sale", payment: "Payment",
};

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function rangeQS(p: string): string {
  const t = new Date(); const Y = t.getFullYear(); const M = t.getMonth();
  if (p === "day") return `&start=${iso(t)}&end=${iso(t)}`;
  if (p === "week") {
    const dow = (t.getDay() + 6) % 7;               // Monday = 0, like the desktop
    const s = new Date(Y, M, t.getDate() - dow);
    const e = new Date(s); e.setDate(s.getDate() + 6);
    return `&start=${iso(s)}&end=${iso(e)}`;
  }
  if (p === "month") return `&start=${iso(new Date(Y, M, 1))}&end=${iso(new Date(Y, M + 1, 0))}`;
  if (p === "year") return `&start=${iso(new Date(Y, 0, 1))}&end=${iso(new Date(Y, 11, 31))}`;
  return "";
}

function KindBadge({ kind }: { kind: string }) {
  const c = KIND_TONE[kind] || "#64748b";
  return (
    <span style={{
      display: "inline-block", background: `color-mix(in srgb, ${c} 16%, transparent)`,
      color: c, padding: "2px 10px", borderRadius: 999, fontWeight: 600, fontSize: 12,
    }}>{KIND_LABEL[kind] || kind}</span>
  );
}

export default function SearchPage() {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [period, setPeriod] = useState("all");
  const [results, setResults] = useState<Result[]>([]);
  const [searched, setSearched] = useState(false);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function doSearch(p = period) {
    setBusy(true);
    try {
      const d = await api.get<{ results: Result[] }>(`/search?q=${encodeURIComponent(q.trim())}${rangeQS(p)}`);
      setResults(d.results); setSearched(true);
    } catch (e) { toast.error(e instanceof ApiError ? e.message : "Couldn't reach the API."); }
    finally { setBusy(false); }
  }
  function onPeriod(p: string) { setPeriod(p); doSearch(p); }   // period changes the query -> refetch

  // Type filter is client-side (the API already returns each kind independently).
  const shown = kind ? results.filter((r) => r.kind === kind) : results;

  return (
    <div>
      <div className="toolbar" style={{ alignItems: "center" }}>
        <div className="search-wrap">
          <Icon name="search" size={16} />
          <input ref={inputRef} className="input" placeholder="Type a name, phone, or vehicle…"
            value={q} onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") doSearch(); }} />
        </div>
        <span className="tb-lbl">Type</span>
        <select className="input" style={{ maxWidth: 150 }} value={kind} onChange={(e) => setKind(e.target.value)}>
          {KINDS.map((k) => <option key={k.v} value={k.v}>{k.label}</option>)}
        </select>
        <span className="tb-lbl">Period</span>
        <select className="input" style={{ maxWidth: 130 }} value={period} onChange={(e) => onPeriod(e.target.value)}>
          {PERIODS.map((p) => <option key={p.v} value={p.v}>{p.label}</option>)}
        </select>
        <button className="btn" onClick={() => doSearch()} disabled={busy}>
          <Icon name="search" size={15} /> {busy ? "Searching…" : "Search"}
        </button>
      </div>

      {searched && (
        <div className="set-note" style={{ padding: "0 4px 8px", fontWeight: 600 }}>
          {shown.length ? `Results: ${shown.length}` : "No results"}
        </div>
      )}

      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr>
            <th style={{ textAlign: "left" }}>Type</th><th style={{ textAlign: "left" }}>Date</th>
            <th style={{ textAlign: "left" }}>Name</th><th style={{ textAlign: "left" }}>Detail</th>
            <th className="right">Amount</th>
          </tr></thead>
          <tbody>
            {shown.length === 0 && (
              <tr><td colSpan={5} className="empty">{searched ? "No results." : "Type a name, phone, or vehicle and press Search."}</td></tr>
            )}
            {shown.map((r, i) => (
              <tr key={i}>
                <td><KindBadge kind={r.kind} /></td>
                <td>{r.date || "—"}</td>
                <td>{r.name || "—"}</td>
                <td>{r.detail || "—"}</td>
                <td className="right">{r.amount || ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
