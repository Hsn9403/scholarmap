"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, FileText, RefreshCw } from "lucide-react";
import { resolveAnalysis, resolveKey } from "@/lib/analyze";
import { useT } from "@/lib/i18n";
import { CenteredSpinner, EmptyState } from "@/components/shared/empty-state";

export default function ConfirmReusePage() {
  return (
    <Suspense fallback={<CenteredSpinner />}>
      <ConfirmReuseContent />
    </Suspense>
  );
}

function ConfirmReuseContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const t = useT();
  const name = searchParams.get("name") ?? "";

  const { data, isLoading } = useQuery({
    queryKey: resolveKey(name, false),
    queryFn: () => resolveAnalysis(name, false),
    enabled: !!name,
    staleTime: 5 * 60 * 1000,
  });

  function viewExisting() {
    window.location.href = `/report/${encodeURIComponent(name)}`;
  }

  if (!name) return <EmptyState message={t("error_no_name")} />;
  if (isLoading) return <CenteredSpinner />;

  // The report vanished between the search and this screen — fall back to a fresh run
  if (data?.action !== "reuse") {
    return (
      <EmptyState message={t("reuse_gone")} />
    );
  }

  const existing = data.existing;

  return (
    <div className="max-w-4xl mx-auto w-full px-4 py-6">
      <div className="mb-4">
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-800 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          {t("back_to_home")}
        </Link>
      </div>

      <div
        className="relative rounded-2xl overflow-hidden"
        style={{
          background: "linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%)",
          boxShadow: "0 4px 20px rgba(0, 102, 204, 0.08)",
          border: "1px solid rgba(20, 184, 166, 0.1)",
        }}
      >
        <div className="p-8">
          {/* Header */}
          <div className="flex items-center space-x-3 mb-6">
            <div
              className="w-12 h-12 rounded-xl flex items-center justify-center"
              style={{
                background: "linear-gradient(135deg, #EFF6FF, #DBEAFE)",
                border: "1px solid rgba(0, 102, 204, 0.15)",
              }}
            >
              <FileText className="w-6 h-6" style={{ color: "#0066CC" }} />
            </div>
            <div>
              <h2 className="text-2xl font-bold" style={{ color: "#1E293B" }}>
                {t("reuse_title")}
              </h2>
              <p className="text-sm text-gray-500">
                {t("reuse_subtitle")}
              </p>
            </div>
          </div>

          {/* Existing data card */}
          <div
            className="mb-8 p-8 rounded-2xl"
            style={{
              border: "2px solid rgba(0, 102, 204, 0.2)",
              background: "linear-gradient(135deg, #EFF6FF, #F0FDFA)",
              boxShadow: "0 4px 16px rgba(0, 102, 204, 0.08)",
            }}
          >
            <div className="space-y-5">
              <Row label={t("table_researcher")}>
                <span className="text-xl font-bold" style={{ color: "#0066CC" }}>
                  {existing.name}
                </span>
              </Row>

              {existing.affiliation && (
                <Row label={t("table_affiliation")}>
                  <span className="text-base text-gray-700 text-right max-w-xs">
                    {existing.affiliation.length > 80
                      ? existing.affiliation.slice(0, 80) + "..."
                      : existing.affiliation}
                  </span>
                </Row>
              )}

              {existing.h_index != null && (
                <Row label={t("metric_hindex")}>
                  <span
                    className="inline-flex items-center px-4 py-1.5 rounded-full text-lg font-bold text-white"
                    style={{ background: "linear-gradient(135deg, #0066CC, #0052A3)" }}
                  >
                    {existing.h_index}
                  </span>
                </Row>
              )}

              {existing.created_at && (
                <Row label={t("reuse_generated_on")}>
                  <span className="text-base text-gray-700">{existing.created_at}</span>
                </Row>
              )}
            </div>
          </div>

          {/* Options */}
          <p className="text-center text-gray-600 mb-6">
            {t("reuse_question")}
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <OptionButton
              onClick={viewExisting}
              accent="#14B8A6"
              accentDark="#0D9488"
              background="linear-gradient(135deg, #F0FDFA, #CCFBF1)"
              icon={<CheckCircle2 className="w-6 h-6 text-white" />}
              title={t("reuse_view_existing")}
              subtitle={t("reuse_view_existing_sub")}
            />
            <OptionButton
              onClick={() => router.push(`/disambiguation?name=${encodeURIComponent(name)}`)}
              accent="#0066CC"
              accentDark="#0052A3"
              background="linear-gradient(135deg, #EFF6FF, #DBEAFE)"
              icon={<RefreshCw className="w-6 h-6 text-white" />}
              title={t("reuse_new_analysis")}
              subtitle={t("reuse_new_analysis_sub")}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-base font-medium text-gray-500">{label}</span>
      {children}
    </div>
  );
}

function OptionButton({
  onClick,
  accent,
  accentDark,
  background,
  icon,
  title,
  subtitle,
}: {
  onClick: () => void;
  accent: string;
  accentDark: string;
  background: string;
  icon: React.ReactNode;
  title: string;
  subtitle: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full p-6 rounded-xl border-2 transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5"
      style={{ borderColor: accent, background }}
      onMouseOver={(e) => (e.currentTarget.style.borderColor = accentDark)}
      onMouseOut={(e) => (e.currentTarget.style.borderColor = accent)}
    >
      <div className="flex flex-col items-center space-y-3">
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center"
          style={{ background: `linear-gradient(135deg, ${accent}, ${accentDark})` }}
        >
          {icon}
        </div>
        <div>
          <h4 className="text-lg font-semibold mb-1" style={{ color: "#1E293B" }}>
            {title}
          </h4>
          <p className="text-sm text-gray-600">{subtitle}</p>
        </div>
      </div>
    </button>
  );
}
