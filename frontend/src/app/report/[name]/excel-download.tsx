"use client";

import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { fetcher } from "@/lib/fetcher";
import { ExcelReadySchema } from "@/types";
import { useT } from "@/lib/i18n";

const POLL_MS = 2000;
const MAX_ATTEMPTS = 90; // 3 minutes

interface ExcelDownloadProps {
  researcherName: string;
  /** Known URL when the file already existed at page load. */
  initialUrl?: string | null;
}

/**
 * Excel export button. The pipeline writes the file slightly after the report
 * becomes viewable, so when it is missing this polls until it lands and then
 * swaps the spinner for a download link. Gives up silently after 3 minutes.
 */
export function ExcelDownload({ researcherName, initialUrl }: ExcelDownloadProps) {
  const t = useT();
  const [url, setUrl] = useState<string | null>(initialUrl ?? null);
  const [gaveUp, setGaveUp] = useState(false);

  useEffect(() => {
    if (url) return;

    let attempts = 0;
    let stopped = false;

    const timer = setInterval(async () => {
      if (stopped) return;
      attempts++;
      if (attempts > MAX_ATTEMPTS) {
        clearInterval(timer);
        setGaveUp(true);
        return;
      }
      try {
        const raw = await fetcher<unknown>(
          `/api/excel_ready/${encodeURIComponent(researcherName)}`
        );
        const parsed = ExcelReadySchema.safeParse(raw);
        if (parsed.success && parsed.data.ready) {
          clearInterval(timer);
          setUrl(parsed.data.url);
        }
      } catch {
        // réseau, réessayer au prochain tick
      }
    }, POLL_MS);

    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [url, researcherName]);

  if (gaveUp) return null;

  if (!url) {
    return (
      <button
        className="px-5 py-2.5 rounded-xl font-medium flex items-center space-x-2 cursor-default"
        style={{ background: "#EFF6FF", color: "#3B82F6", border: "1px solid #BFDBFE" }}
        disabled
      >
        <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        <span>{t("report_excel_pending")}</span>
      </button>
    );
  }

  return (
    <a
      href={url}
      download
      className="inline-flex px-5 py-2.5 rounded-xl font-medium transition-all duration-200 items-center space-x-2 hover:shadow-lg hover:-translate-y-0.5"
      style={{ background: "linear-gradient(135deg, #14B8A6, #0D9488)", color: "white" }}
    >
      <Download className="w-5 h-5" />
      <span>{t("report_download")}</span>
    </a>
  );
}
