"use client";

import { Suspense, useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Building2, Users } from "lucide-react";
import { fetcher } from "@/lib/fetcher";
import { Header } from "@/components/layout/header";
import { InfoTooltip } from "@/components/shared/info-tooltip";
import { useT } from "@/lib/i18n";
import { CenteredSpinner, EmptyState } from "@/components/shared/empty-state";
import { ReportDataSchema, type ReportData } from "@/types";
import { ExcelDownload } from "./excel-download";
import { MetricCards } from "./metric-cards";

export default function ReportPage() {
  return (
    <Suspense fallback={<CenteredSpinner />}>
      <ReportContent />
    </Suspense>
  );
}

function ReportContent() {
  const params = useParams();
  const searchParams = useSearchParams();
  const t = useT();

  const rawName = Array.isArray(params.name) ? params.name[0] : (params.name ?? "");
  const researcherName = decodeURIComponent(rawName);
  // ?embed=1 renders the report without the header, for embedding in another page
  const embed = searchParams.get("embed") === "1";

  const { data, isLoading, isError } = useQuery<ReportData>({
    queryKey: ["report", researcherName],
    queryFn: async () => {
      const raw = await fetcher<unknown>(`/api/report/${encodeURIComponent(researcherName)}`);
      return ReportDataSchema.parse(raw);
    },
    enabled: !!researcherName,
    staleTime: 5 * 60 * 1000,
  });

  // The graph iframe cannot navigate the top window itself, so it asks us to
  useEffect(() => {
    function onMessage(e: MessageEvent) {
      const msg = e.data;
      if (!msg || typeof msg !== "object") return;
      // The graph is sandboxed and renders external strings: only follow web links
      if (msg.type === "openUrl" && typeof msg.url === "string" && /^https?:\/\//i.test(msg.url)) {
        window.open(msg.url, "_blank", "noopener,noreferrer");
      }
    }
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  const body = isLoading ? (
    <CenteredSpinner />
  ) : isError || !data ? (
    <EmptyState message={t("report_unavailable")} />
  ) : (
    <Report data={data} />
  );

  const main = (
    <main className="flex-1 flex flex-col px-4 sm:px-6 lg:px-8 py-8">{body}</main>
  );

  // Embedded: the parent page shows the chrome
  if (embed) return main;

  return (
    <>
      <Header />
      {main}
    </>
  );
}

function Report({ data }: { data: ReportData }) {
  const t = useT();
  const { researcher, graph_url, excel_url } = data;

  return (
    <div className="max-w-7xl mx-auto w-full">
      {/* ── Profile header ── */}
      <div
        className="relative overflow-hidden rounded-2xl mb-8"
        style={{
          background: "linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%)",
          boxShadow: "0 4px 20px rgba(0, 102, 204, 0.08)",
          border: "1px solid rgba(20, 184, 166, 0.1)",
        }}
      >
        <div
          className="absolute top-0 right-0 w-64 h-64 opacity-5"
          style={{ background: "radial-gradient(circle, #0066CC 0%, transparent 70%)" }}
        />
        <div
          className="absolute bottom-0 left-0 w-48 h-48 opacity-5"
          style={{ background: "radial-gradient(circle, #14B8A6 0%, transparent 70%)" }}
        />

        <div className="relative p-8">
          <div className="flex items-center flex-wrap gap-3 mb-2">
            <h1 className="text-3xl font-bold" style={{ color: "#1E293B" }}>
              {researcher.name}
            </h1>
            {researcher.specialty_tags.map((tag) => (
              <span
                key={tag}
                className="px-3 py-1 text-xs font-semibold rounded-full"
                style={{
                  background: "linear-gradient(135deg, #EFF6FF, #F0FDFA)",
                  color: "#0066CC",
                  border: "1px solid rgba(0, 102, 204, 0.2)",
                }}
              >
                {tag}
              </span>
            ))}
          </div>

          {researcher.affiliation && (
            <div className="flex items-center space-x-2 mb-6">
              <Building2 className="w-4 h-4 text-gray-400 flex-shrink-0" />
              <p className="text-gray-600">{researcher.affiliation}</p>
              <InfoTooltip>{t("affiliation_tooltip")}</InfoTooltip>
            </div>
          )}

          <MetricCards researcher={researcher} />
        </div>
      </div>

      {/* ── Network graph ── */}
      <div className="relative" style={{ background: "white" }}>
        <div className="px-6 pt-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center space-x-3">
              <Users className="w-8 h-8" style={{ color: "#0066CC" }} strokeWidth={2} />
              <div>
                <h2 className="text-xl font-bold" style={{ color: "#1E293B" }}>
                  {t("network_title")}
                </h2>
                <p className="text-sm text-gray-500">
                  {t("network_subtitle")}
                </p>
              </div>
            </div>

            <ExcelDownload researcherName={researcher.name} initialUrl={excel_url} />
          </div>

          {/* Usage instructions */}
          <div className="flex items-stretch gap-3 mb-4">
            <UsageHint
              title={t("usage_thickness_title")}
              desc={t("usage_thickness_desc")}
            />
            <UsageHint
              title={t("usage_filters_title")}
              desc={t("usage_filters_desc")}
            />
          </div>
        </div>

        {graph_url ? (
          <iframe
            src={graph_url}
            sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox allow-modals"
            className="w-full h-[1000px]"
            style={{
              display: "block",
              border: "none",
              outline: "none",
              background: "transparent",
            }}
            title={`Réseau de ${researcher.name}`}
          />
        ) : (
          <div
            className="mx-6 mb-6 rounded-xl h-[1000px] flex flex-col items-center justify-center"
            style={{
              border: "2px dashed rgba(0, 102, 204, 0.2)",
              background: "linear-gradient(135deg, #F8FAFC, #EFF6FF)",
            }}
          >
            <svg
              className="w-16 h-16 text-gray-300 mb-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
              />
            </svg>
            <p className="text-gray-500 font-medium">{t("graph_missing_title")}</p>
            <p className="text-sm text-gray-400 mt-1">{t("graph_missing_desc")}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function UsageHint({ title, desc }: { title: string; desc: string }) {
  return (
    <div
      className="inline-flex items-start gap-3 rounded-xl px-5 py-4 flex-1"
      style={{
        border: "1px solid rgba(0, 102, 204, 0.15)",
        background: "rgba(0, 102, 204, 0.06)",
      }}
    >
      <div>
        <p className="text-sm font-semibold" style={{ color: "#0066CC" }}>
          {title}
        </p>
        <p className="text-sm" style={{ color: "#475569" }}>
          {desc}
        </p>
      </div>
    </div>
  );
}
