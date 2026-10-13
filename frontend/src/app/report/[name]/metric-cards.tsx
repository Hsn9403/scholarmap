import { BookOpen, FileText, GraduationCap } from "lucide-react";
import { InfoTooltip } from "@/components/shared/info-tooltip";
import { useT } from "@/lib/i18n";
import type { ReportResearcher } from "@/types";

/** Truncate a patent title the way the report has always shown them. */
function shortLabel(label: string, max = 60) {
  return label.length > max ? label.slice(0, max) + "…" : label;
}

/** H-index, patents and recent co-publications — the three headline metrics. */
export function MetricCards({ researcher }: { researcher: ReportResearcher }) {
  const t = useT();
  const ai = researcher.h_index_ai_assessment;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* ── H-index ── */}
      <div
        className="p-4 rounded-xl"
        style={{
          background: "linear-gradient(135deg, #EFF6FF, #FFFFFF)",
          border: "1px solid rgba(0, 102, 204, 0.1)",
        }}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center space-x-2">
            <GraduationCap className="w-8 h-8" style={{ color: "#0066CC" }} strokeWidth={2} />
            <p className="text-base font-semibold text-gray-700 uppercase tracking-wide">
              {t("metric_hindex")}
            </p>
          </div>
          <InfoTooltip align="right" widthClass="w-72">
            {t("hindex_tooltip")}
          </InfoTooltip>
        </div>

        {researcher.h_index ? (
          <div>
            <p className="text-3xl font-bold" style={{ color: "#0066CC" }}>
              {researcher.h_index}
            </p>
            {ai ? (
              <>
                <p className="text-sm font-semibold mt-1" style={{ color: "#0066CC" }}>
                  Top {ai.percentile}%
                  {ai.field && <>&nbsp;&bull;&nbsp;{ai.field}</>}
                </p>
                {ai.scale && (
                  <p className="text-xs text-gray-400 mt-1 italic leading-relaxed">{ai.scale}</p>
                )}
              </>
            ) : (
              researcher.h_index_percentile != null && (
                <p className="text-sm text-gray-500 mt-1">
                  Top {researcher.h_index_percentile}%
                </p>
              )
            )}
          </div>
        ) : (
          <p className="text-2xl font-bold text-gray-400">N/A</p>
        )}
      </div>

      {/* ── Patents ── */}
      <div
        className="p-4 rounded-xl"
        style={{
          background: "linear-gradient(135deg, #F0FDFA, #FFFFFF)",
          border: "1px solid rgba(20, 184, 166, 0.1)",
        }}
      >
        <div className="flex items-center space-x-2 mb-2">
          <FileText className="w-8 h-8" style={{ color: "#14B8A6" }} strokeWidth={2} />
          <p className="text-base font-semibold text-gray-700 uppercase tracking-wide">
            {t("metric_patents")}
          </p>
        </div>
        <p className="text-2xl font-bold mb-3" style={{ color: "#14B8A6" }}>
          {researcher.patents_count}
        </p>

        {researcher.patents.length > 0 && (
          <div style={{ maxHeight: 200, overflowY: "auto" }}>
            <ul className="space-y-1.5 text-sm">
              {researcher.patents.map((p, i) => (
                <li key={p.id ?? `${p.label}-${i}`}>
                  {p.url ? (
                    <a
                      href={p.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-teal-600 hover:text-teal-700 hover:underline break-words"
                      title={p.label}
                    >
                      {shortLabel(p.label)}
                    </a>
                  ) : (
                    <span className="text-gray-600">{shortLabel(p.label)}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* ── Recent co-publications ── */}
      <div
        className="p-4 rounded-xl"
        style={{
          background: "linear-gradient(135deg, #EFF6FF, #FFFFFF)",
          border: "1px solid rgba(6, 182, 212, 0.1)",
        }}
      >
        <div className="flex items-center space-x-2 mb-2">
          <BookOpen className="w-8 h-8" style={{ color: "#06B6D4" }} strokeWidth={2} />
          <p className="text-base font-semibold text-gray-700 uppercase tracking-wide">
            {t("metric_copub")}
          </p>
        </div>
        <p className="text-2xl font-bold" style={{ color: "#06B6D4" }}>
          {researcher.recent_publications}
        </p>
        <p className="text-xs text-gray-500 mt-1">{t("metric_copub_year")}</p>
      </div>
    </div>
  );
}
