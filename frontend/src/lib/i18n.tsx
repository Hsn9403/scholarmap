"use client";

import { createContext, useContext } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fetcher } from "@/lib/fetcher";

export type Lang = "fr" | "en";

interface I18nPayload {
  lang: Lang;
  translations: Record<string, string>;
}

interface I18nValue {
  lang: Lang;
  /**
   * Translate a key from webapp/translations/<lang>.json.
   * `vars` fills `{placeholders}`. Unknown keys return the key itself, which
   * makes a missing translation obvious rather than silently empty.
   */
  t: (key: string, vars?: Record<string, string | number>) => string;
  setLang: (lang: Lang) => Promise<void>;
}

const I18nContext = createContext<I18nValue | null>(null);

const EMPTY: Record<string, string> = {};

/**
 * Serves translations straight from Flask so `webapp/translations/*.json` stays
 * the single source of truth for both the Jinja pages and React.
 */
export function I18nProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient();

  const { data, isLoading } = useQuery<I18nPayload>({
    queryKey: ["i18n"],
    queryFn: () => fetcher<I18nPayload>("/api/i18n"),
    staleTime: Infinity,
    retry: 1,
  });

  const translations = data?.translations ?? EMPTY;

  const value: I18nValue = {
    lang: data?.lang ?? "fr",
    t: (key, vars) => {
      let out = translations[key] ?? key;
      if (vars) {
        for (const [k, v] of Object.entries(vars)) {
          out = out.replaceAll(`{${k}}`, String(v));
        }
      }
      return out;
    },
    setLang: async (lang) => {
      await api.post("/api/i18n/lang", { lang });
      // Flask keeps the language in the session, so everything server-rendered
      // (graph iframes, Excel, remaining Jinja pages) must be refetched too.
      await qc.invalidateQueries();
    },
  };

  // Gate the first paint so no screen flashes untranslated keys
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-[#0066CC] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

/** Access the current language and translator. Must be under I18nProvider. */
export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within an I18nProvider");
  return ctx;
}

/** Shorthand for the common case: just the translate function. */
export function useT() {
  return useI18n().t;
}
