"use client";

import { useEffect, useRef, useState } from "react";

/* Type-to-filter single select — mirrors the desktop SearchableComboBox
   (editable, case-insensitive "contains" match, no free text insert). */

export type Opt = { value: string; label: string };

export function SearchSelect({
  value, options, onChange, placeholder = "Search…",
}: {
  value: string; options: Opt[]; onChange: (v: string) => void; placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hi, setHi] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value);
  const filtered = q ? options.filter((o) => o.label.toLowerCase().includes(q.toLowerCase())) : options;

  useEffect(() => {
    function onDoc(e: MouseEvent) { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  function pick(o: Opt) { onChange(o.value); setOpen(false); setQ(""); }

  return (
    <div className="ss" ref={ref}>
      <input
        className="input"
        placeholder={placeholder}
        value={open ? q : (selected?.label ?? "")}
        onFocus={() => { setOpen(true); setQ(""); setHi(0); }}
        onChange={(e) => { setQ(e.target.value); setOpen(true); setHi(0); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setHi((h) => Math.min(h + 1, filtered.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)); }
          else if (e.key === "Enter") { e.preventDefault(); if (open && filtered[hi]) pick(filtered[hi]); }
          else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && (
        <div className="ss-pop">
          {filtered.length === 0 && <div className="ss-empty">No matches</div>}
          {filtered.map((o, i) => (
            <div
              key={o.value}
              className={"ss-opt" + (i === hi ? " hi" : "") + (o.value === value ? " sel" : "")}
              onMouseEnter={() => setHi(i)}
              onMouseDown={(e) => { e.preventDefault(); pick(o); }}
            >
              {o.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
