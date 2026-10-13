"use client";

import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Search, Users, X } from "lucide-react";
import { isAxiosError } from "axios";
import { resolveAnalysis, resolveKey, startAnalysis } from "@/lib/analyze";
import { OACandidateCard } from "@/components/shared/oa-candidate-card";
import { useT } from "@/lib/i18n";
import { CenteredSpinner, EmptyState } from "@/components/shared/empty-state";
import type { OACandidate } from "@/types";

export default function DisambiguationPage() {
  return (
    <Suspense fallback={<CenteredSpinner />}>
      <DisambiguationContent />
    </Suspense>
  );
}

function DisambiguationContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const t = useT();
  const name = searchParams.get("name") ?? "";

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  // force_new: this screen only ever asks OpenAlex for profiles, never for a
  // cached report. The landing page seeds this same key so there is no refetch.
  const { data, isLoading } = useQuery({
    queryKey: resolveKey(name, true),
    queryFn: () => resolveAnalysis(name, true),
    enabled: !!name,
    staleTime: 5 * 60 * 1000,
  });

  const candidates: OACandidate[] = useMemo(
    () => (data?.action === "disambiguate" ? data.candidates : []),
    [data]
  );

  const visible = useMemo(() => {
    const kw = filter.trim().toLowerCase();
    if (!kw) return candidates;
    return candidates.filter(
      (c) =>
        c.name.toLowerCase().includes(kw) ||
        c.all_affiliations.some((a) => a.toLowerCase().includes(kw))
    );
  }, [candidates, filter]);

  // Selection defaults to the first visible candidate, and falls back to it when
  // the filter hides the one that was picked — never launch an invisible profile.
  const effectiveId =
    selectedId && visible.some((c) => c.openalex_id === selectedId)
      ? selectedId
      : (visible[0]?.openalex_id ?? null);
  const selected = visible.find((c) => c.openalex_id === effectiveId);

  async function handleAnalyze() {
    if (!selected) return;
    setStarting(true);
    setStartError(null);
    try {
      // The selected profile's canonical name wins over what was typed
      // (ex: "Paul Fontaine" → "Paul-Yann Fontaine")
      const { task_id } = await startAnalysis({
        researcherName: selected.name,
        openalexId: selected.openalex_id,
      });
      router.push(`/analyze/${task_id}`);
    } catch (err) {
      setStartError(
        isAxiosError(err) && err.response?.status === 429
          ? t("analysis_limit_reached")
          : t("disambig_fetch_error"),
      );
      setStarting(false);
    }
  }

  if (!name) {
    return <EmptyState message={t("error_no_name")} />;
  }
  if (isLoading) {
    return <CenteredSpinner />;
  }
  if (data?.action === "error") {
    return <EmptyState message={data.error} />;
  }
  if (candidates.length === 0) {
    return <EmptyState message={t("disambig_no_openalex_found")} />;
  }

  const single = candidates.length === 1;

  return (
    <div className="max-w-4xl mx-auto w-full px-4 py-6">
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
              style={{ background: "linear-gradient(135deg, #EFF6FF, #DBEAFE)" }}
            >
              <Users className="w-6 h-6" style={{ color: "#0066CC" }} />
            </div>
            <div>
              <h2 className="text-2xl font-bold" style={{ color: "#1E293B" }}>
                {single ? t("disambig_title_single") : t("disambig_title_multiple")}
              </h2>
              <p className="text-sm text-gray-500">
                {single ? t("disambig_oa_single") : t("disambig_oa_multiple")}{" "}
                <strong>&quot;{name}&quot;</strong>. {t("disambig_select_right")}
              </p>
            </div>
          </div>

          {/* Affiliation keyword filter */}
          <div className="mb-4">
            <div className="flex items-center gap-2 px-3 py-2.5 rounded-xl border border-gray-200 bg-gray-50 focus-within:ring-2 focus-within:ring-purple-200 focus-within:border-purple-300 transition-all">
              <Search className="w-4 h-4 text-gray-400 flex-shrink-0" />
              <input
                type="text"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder={t("disambig_filter_placeholder")}
                className="flex-1 bg-transparent text-sm text-gray-700 placeholder-gray-400 outline-none min-w-0"
              />
              {filter && (
                <button
                  type="button"
                  onClick={() => setFilter("")}
                  className="text-gray-400 hover:text-gray-600 transition-colors flex-shrink-0"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
            {filter && visible.length === 0 && (
              <p className="text-sm text-gray-400 mt-2 text-center">
                {t("disambig_no_match")}
              </p>
            )}
          </div>

          {/* Candidates */}
          <div className="space-y-3 mb-8">
            {visible.map((c) => (
              <OACandidateCard
                key={c.openalex_id}
                candidate={c}
                selected={c.openalex_id === effectiveId}
                onSelect={() => setSelectedId(c.openalex_id)}
              />
            ))}
          </div>

          {startError && (
            <p className="mb-4 text-center text-sm font-medium text-red-600">{startError}</p>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between mt-8">
            <Link
              href="/"
              className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              {t("back")}
            </Link>
            <button
              type="button"
              onClick={handleAnalyze}
              disabled={starting || !selected}
              className="px-8 py-3 rounded-xl font-semibold text-white transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5 disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:translate-y-0"
              style={{ background: "linear-gradient(135deg, #0066CC, #0052A3)" }}
            >
              {starting ? t("disambig_searching") : t("disambig_analyze_button")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
