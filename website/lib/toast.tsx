"use client";

/* Slide-in toast cards + a styled confirm dialog — mirrors the desktop's
   timber.ui.toast (top-right cards, coloured badge + accent stripe) and
   design.confirm (tinted-header Yes/No dialog). */

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { Icon } from "@/components/Icon";

type Kind = "success" | "error" | "warning" | "info";
type Toast = { id: number; kind: Kind; text: string };
type Confirm = { id: number; title: string; text: string; danger: boolean; okText: string; resolve: (v: boolean) => void };

const KIND: Record<Kind, { color: string; icon: string }> = {
  success: { color: "#16a34a", icon: "check" },
  error: { color: "#dc2626", icon: "x" },
  warning: { color: "#d97706", icon: "alert-triangle" },
  info: { color: "#2563eb", icon: "info" },
};
const DURATION: Record<Kind, number> = { success: 2600, info: 2600, warning: 4200, error: 4800 };

type Api = {
  success: (t: string) => void; error: (t: string) => void;
  warning: (t: string) => void; info: (t: string) => void;
  confirm: (o: { title: string; text: string; danger?: boolean; okText?: string }) => Promise<boolean>;
};
const Ctx = createContext<Api | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [confirms, setConfirms] = useState<Confirm[]>([]);

  const notify = useCallback((kind: Kind, text: string) => {
    if (!text) return;
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), DURATION[kind]);
  }, []);

  const confirm = useCallback((o: { title: string; text: string; danger?: boolean; okText?: string }) =>
    new Promise<boolean>((resolve) => {
      const id = Date.now() + Math.random();
      setConfirms((c) => [...c, { id, title: o.title, text: o.text, danger: !!o.danger, okText: o.okText || "Yes", resolve }]);
    }), []);

  function close(id: number, val: boolean) {
    setConfirms((c) => c.filter((x) => { if (x.id === id) { x.resolve(val); return false; } return true; }));
  }

  // Stable value: notify/confirm are useCallback([]), so this object is created
  // once and never changes identity. Without this, every toast (and its auto-
  // dismiss) re-rendered the provider with a NEW value, refiring every page's
  // load useEffect (which lists `toast` in its deps) — a redundant refetch on
  // each toast, doubling the cost of heavy pages on the cloud.
  const api = useMemo<Api>(() => ({
    success: (t) => notify("success", t), error: (t) => notify("error", t),
    warning: (t) => notify("warning", t), info: (t) => notify("info", t), confirm,
  }), [notify, confirm]);

  return (
    <Ctx.Provider value={api}>
      {children}
      <div className="toast-wrap">
        {toasts.map((t) => (
          <div key={t.id} className="toast" onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}>
            <span className="toast-accent" style={{ background: KIND[t.kind].color }} />
            <span className="toast-badge" style={{ background: KIND[t.kind].color }}><Icon name={KIND[t.kind].icon} size={17} /></span>
            <span className="toast-msg">{t.text}</span>
          </div>
        ))}
      </div>
      {confirms.map((cf) => {
        const tone = cf.danger ? "#f43f5e" : "#f59e0b";
        return (
          <div key={cf.id} className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) close(cf.id, false); }}>
            <div className="modal" style={{ maxWidth: 430 }}>
              <div className="dlg-head" style={{ background: `linear-gradient(90deg, color-mix(in srgb, ${tone} 15%, var(--surface)), color-mix(in srgb, ${tone} 5%, var(--surface)))` }}>
                <span className="dlg-chip" style={{ background: `color-mix(in srgb, ${tone} 18%, transparent)`, color: tone }}>
                  <Icon name="alert-triangle" size={21} />
                </span>
                <span className="dlg-title">{cf.title}</span>
              </div>
              <div className="modal-body"><p style={{ margin: 0, fontSize: 13 }}>{cf.text}</p></div>
              <div className="modal-foot">
                <button className="btn-ghost" onClick={() => close(cf.id, false)}>No</button>
                <button className={cf.danger ? "btn btn-danger-lg" : "btn"} onClick={() => close(cf.id, true)}>{cf.okText}</button>
              </div>
            </div>
          </div>
        );
      })}
    </Ctx.Provider>
  );
}

export function useToast(): Api {
  const c = useContext(Ctx);
  if (!c) throw new Error("useToast must be used inside <ToastProvider>");
  return c;
}
