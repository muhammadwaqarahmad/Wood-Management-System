"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { useLang } from "./i18n";

/* The business name, fetched once from the shared API (GET /settings/business is
   public, so the login screen shows it too). Every header/label/title reads it
   from here; Settings calls refresh() after saving so the whole site updates
   live. Env value on the API is the default until an admin sets one. */

type BusinessContextValue = {
  nameEn: string;
  nameUr: string;
  name: string;            // language-appropriate
  refresh: () => Promise<void>;
};

const DEFAULT_EN = "Abdul Sattar Woods";
const DEFAULT_UR = "عبدالستار ووڈز";
const Ctx = createContext<BusinessContextValue | null>(null);

export function BusinessProvider({ children }: { children: ReactNode }) {
  const { lang } = useLang();
  const [nameEn, setNameEn] = useState(DEFAULT_EN);
  const [nameUr, setNameUr] = useState(DEFAULT_UR);

  const refresh = useCallback(async () => {
    try {
      const d = await api.get<{ name_en: string; name_ur: string }>("/settings/business");
      if (d.name_en) setNameEn(d.name_en);
      if (d.name_ur) setNameUr(d.name_ur);
    } catch {
      /* API unreachable — keep the defaults so the UI still renders. */
    }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const name = lang === "ur" ? nameUr : nameEn;
  // Keep the browser tab title in sync too (part of "everywhere").
  useEffect(() => { if (typeof document !== "undefined" && name) document.title = name; }, [name]);

  const value = useMemo(() => ({ nameEn, nameUr, name, refresh }), [nameEn, nameUr, name, refresh]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useBusiness(): BusinessContextValue {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useBusiness must be used inside <BusinessProvider>");
  return ctx;
}
