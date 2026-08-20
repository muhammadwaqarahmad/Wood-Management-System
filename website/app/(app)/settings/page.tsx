"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { useLang, type Lang } from "@/lib/i18n";
import { applyTheme, currentTheme, type Theme } from "@/lib/theme";
import { useToast } from "@/lib/toast";
import { useBusiness } from "@/lib/business";
import { Icon } from "@/components/Icon";

/* Mirrors the desktop SettingsScreen (timber/ui/screens/settings_screen.py):
   Appearance, Backup folder, Auto-backup, Backup/Restore, Audit Log. Backup and
   restore are FULLY functional here — they drive timber.core.backup on the
   server through /backup/* (admin-gated), and move files with browser
   download/upload. */

type Status = {
  backup_dir: string; auto_on_close: boolean; interval_hours: number;
  keep_days: number; last_backup: string | null;
  backups: { name: string; when: string; size_mb: number }[];
};

function Card({ title, icon, subtitle, children }: {
  title: string; icon: string; subtitle?: string; children: React.ReactNode;
}) {
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-head">
        <span className="chip"><Icon name={icon} size={15} /></span>
        <span className="h">{title}</span>
      </div>
      {subtitle && <p className="set-note" style={{ margin: "-8px 0 12px" }}>{subtitle}</p>}
      {children}
    </div>
  );
}

const LANGS: { v: Lang; label: string }[] = [{ v: "en", label: "English" }, { v: "ur", label: "اردو" }];
const THEMES: { v: Theme; label: string }[] = [{ v: "light", label: "Light" }, { v: "dark", label: "Dark" }];
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);
function ago(iso: string) {
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} hours ago`;
  return `${Math.floor(s / 86400)} days ago`;
}

export default function SettingsPage() {
  const { lang, setLang } = useLang();
  const toast = useToast();
  const business = useBusiness();
  const [pendLang, setPendLang] = useState<Lang>("en");
  const [pendTheme, setPendTheme] = useState<Theme>("light");
  const [bizEn, setBizEn] = useState("");
  const [bizUr, setBizUr] = useState("");

  const [st, setSt] = useState<Status | null>(null);
  const [canBackup, setCanBackup] = useState(true);
  const [sel, setSel] = useState("");
  const [interval, setIntervalH] = useState("12");
  const [keep, setKeep] = useState("30");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setPendLang(lang);
    setPendTheme(currentTheme() === "dark" ? "dark" : "light");
  }, [lang]);
  // Pre-fill the business-name fields from the live value.
  useEffect(() => { setBizEn(business.nameEn); setBizUr(business.nameUr); }, [business.nameEn, business.nameUr]);

  async function saveBusiness() {
    if (!bizEn.trim() && !bizUr.trim()) { toast.warning("Enter a business name."); return; }
    setBusy(true);
    try {
      await api.put("/settings/business", { name_en: bizEn.trim(), name_ur: bizUr.trim() });
      await business.refresh();   // updates headers/login/labels across the site live
      toast.success("Business name updated.");
    } catch (e) { toast.error(errMsg(e, "Could not save the business name.")); }
    finally { setBusy(false); }
  }

  const loadStatus = useCallback(async () => {
    try {
      const s = await api.get<Status>("/backup/status");
      setSt(s); setCanBackup(true);
      setIntervalH(String(s.interval_hours));
      setKeep(String(s.keep_days));
      setSel(s.backups[0]?.name ?? "");
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setCanBackup(false);
      else toast.error(errMsg(e, "Couldn't load backup status."));
    }
  }, [toast]);
  useEffect(() => { loadStatus(); }, [loadStatus]);

  function applyAppearance() {
    setLang(pendLang); applyTheme(pendTheme); toast.success("Saved.");
  }
  async function saveSetting(patch: Record<string, unknown>) {
    try { await api.post("/backup/settings", patch); toast.success("Saved."); await loadStatus(); }
    catch (e) { toast.error(errMsg(e, "Could not save.")); }
  }
  async function backupNow() {
    setBusy(true);
    try {
      const r = await api.post<{ name: string }>("/backup/now");
      await api.download(`/backup/download/${encodeURIComponent(r.name)}`, r.name);
      toast.success("Backup created and downloaded.");
      await loadStatus();
    } catch (e) { toast.error(errMsg(e, "Backup failed.")); }
    finally { setBusy(false); }
  }
  async function downloadSel() {
    if (!sel) { toast.warning("Choose a backup first."); return; }
    try { await api.download(`/backup/download/${encodeURIComponent(sel)}`, sel); }
    catch (e) { toast.error(errMsg(e, "Download failed.")); }
  }
  async function restoreSel() {
    if (!sel) { toast.warning("Choose a backup first."); return; }
    if (!(await toast.confirm({ title: "Restore", text: `Replace the live database with "${sel}"? This overwrites current data.`, danger: true, okText: "Restore" }))) return;
    setBusy(true);
    try { await api.post("/backup/restore", { name: sel }); toast.success("Restored. Reload to see the restored data."); }
    catch (e) { toast.error(errMsg(e, "Restore failed.")); }
    finally { setBusy(false); }
  }
  async function restoreUpload(file: File) {
    if (!(await toast.confirm({ title: "Restore", text: `Replace the live database with "${file.name}"? This overwrites current data.`, danger: true, okText: "Restore" }))) return;
    setBusy(true);
    try { await api.upload("/backup/restore-upload", file); toast.success("Restored. Reload to see the restored data."); await loadStatus(); }
    catch (e) { toast.error(errMsg(e, "Restore failed.")); }
    finally { setBusy(false); }
  }
  async function changeFolder() {
    const dir = prompt("Server backup folder path:", st?.backup_dir ?? "");
    if (!dir || !dir.trim()) return;
    await saveSetting({ backup_dir: dir.trim() });
  }
  const off = !canBackup || busy;

  return (
    <div>
      {/* ---------------- Appearance ---------------- */}
      <Card title="Settings" icon="settings">
        <div className="grid2">
          <label className="fld"><span>Choose language</span>
            <select className="input" value={pendLang} onChange={(e) => setPendLang(e.target.value as Lang)}>
              {LANGS.map((l) => <option key={l.v} value={l.v}>{l.label}</option>)}
            </select>
          </label>
          <label className="fld"><span>Theme</span>
            <select className="input" value={pendTheme} onChange={(e) => setPendTheme(e.target.value as Theme)}>
              {THEMES.map((t) => <option key={t.v} value={t.v}>{t.label}</option>)}
            </select>
          </label>
        </div>
        <div className="set-row"><button className="btn" onClick={applyAppearance}>Apply</button></div>
      </Card>

      {/* ---------------- Business name ---------------- */}
      <Card title="Business name" icon="landmark"
        subtitle="Shown across the app — every page header, the login screen, PDF/Excel exports and the 'we paid' label. Takes effect on the website immediately; the desktop app and exports pick it up on their next start.">
        <div className="grid2">
          <label className="fld"><span>Name (English)</span>
            <input className="input" value={bizEn} onChange={(e) => setBizEn(e.target.value)} disabled={!canBackup} />
          </label>
          <label className="fld"><span>Name (اردو)</span>
            <input className="input" value={bizUr} onChange={(e) => setBizUr(e.target.value)} disabled={!canBackup} />
          </label>
        </div>
        <div className="set-row">
          <button className="btn" onClick={saveBusiness}
            disabled={!canBackup || busy || (!bizEn.trim() && !bizUr.trim())}>
            {busy ? "Saving…" : "Save business name"}
          </button>
        </div>
        {!canBackup && <p className="set-note">Changing the business name needs the admin role.</p>}
      </Card>

      {!canBackup && (
        <div className="card notice" style={{ marginBottom: 16 }}>
          <strong>Backups need the admin role.</strong>
          <p className="set-note">Your account can&apos;t manage backups. Sign in as an administrator.</p>
        </div>
      )}

      {/* ---------------- Backup folder ---------------- */}
      <Card title="Backup folder" icon="database"
        subtitle="Where the server keeps backup files. On the desktop you can point this at a Google Drive folder to auto-upload each backup.">
        <div className="set-row">
          <div className="folder-path">{st?.backup_dir ?? "—"}</div>
          <button className="btn-ghost" onClick={changeFolder} disabled={off}>Change…</button>
        </div>
      </Card>

      {/* ---------------- Auto-backup on exit ---------------- */}
      <Card title="Auto-backup on exit" icon="history">
        <label className="set-chk">
          <input type="checkbox" checked={st?.auto_on_close ?? false} disabled={off}
            onChange={(e) => saveSetting({ auto_on_close: e.target.checked })} />
          Back up automatically when the app closes
        </label>
        <div className="grid3" style={{ marginTop: 12 }}>
          <label className="fld"><span>Auto-backup every</span>
            <div className="in-unit">
              <input className="input" inputMode="numeric" value={interval} disabled={off}
                onChange={(e) => setIntervalH(e.target.value)}
                onBlur={() => saveSetting({ interval_hours: Number(interval) || 0 })} />
              <span className="u">h</span>
            </div>
          </label>
          <label className="fld"><span>Keep backups for</span>
            <div className="in-unit">
              <input className="input" inputMode="numeric" value={keep} disabled={off}
                onChange={(e) => setKeep(e.target.value)}
                onBlur={() => saveSetting({ keep_days: Number(keep) || 0 })} />
              <span className="u">days</span>
            </div>
          </label>
          <label className="fld"><span>Last backup</span>
            {st?.last_backup
              ? <input className="input last-ok" disabled value={`${new Date(st.last_backup).toLocaleString()} (${ago(st.last_backup)})`} />
              : <input className="input last-never" disabled value="Never" />}
          </label>
        </div>
      </Card>

      {/* ---------------- Backup / restore ---------------- */}
      <Card title="Backup now" icon="file-check">
        <div className="set-row">
          <button className="btn" onClick={backupNow} disabled={off}>{busy ? "Working…" : "Backup now"}</button>
        </div>
        <label className="fld" style={{ marginTop: 12 }}>
          <span>Choose a backup file</span>
          <div className="set-row" style={{ marginTop: 0 }}>
            <select className="input" style={{ flex: 1, minWidth: 220 }} value={sel} disabled={off}
              onChange={(e) => setSel(e.target.value)}>
              {(!st || st.backups.length === 0) && <option value="">No backups</option>}
              {st?.backups.map((b) => (
                <option key={b.name} value={b.name}>
                  {new Date(b.when).toLocaleString()}  ({b.size_mb} MB)
                </option>
              ))}
            </select>
            <button className="btn-ghost" onClick={downloadSel} disabled={off || !sel}>Download</button>
            <button className="btn-ghost" onClick={restoreSel} disabled={off || !sel}>Restore</button>
            <button className="btn-ghost" onClick={() => fileRef.current?.click()} disabled={off}>Restore from file…</button>
          </div>
        </label>
        <input ref={fileRef} type="file" hidden
          onChange={(e) => { const f = e.target.files?.[0]; if (f) restoreUpload(f); e.target.value = ""; }} />
      </Card>

      {/* ---------------- Audit log ---------------- */}
      <Card title="Audit Log" icon="history" subtitle="Every create, edit and delete, with who did it and when.">
        <div className="set-row">
          <Link className="btn" href="/audit"><Icon name="history" size={15} /> Audit Log</Link>
        </div>
      </Card>
    </div>
  );
}
