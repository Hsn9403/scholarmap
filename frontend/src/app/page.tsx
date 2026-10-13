"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Network } from "lucide-react";
import { Header } from "@/components/layout/header";
import { resolveAnalysis, resolveKey } from "@/lib/analyze";
import { useT } from "@/lib/i18n";

export default function LandingPage() {
  const t = useT();
  const router = useRouter();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const researcherName = name.trim();
    if (!researcherName) return;

    setError(null);
    setResolving(true);
    try {
      const result = await resolveAnalysis(researcherName);

      if (result.action === "error") {
        setError(result.error);
        setResolving(false);
        return;
      }

      // Seed the destination page's cache so it renders without a second round-trip
      if (result.action === "reuse") {
        qc.setQueryData(resolveKey(researcherName, false), result);
        router.push(`/confirm-reuse?name=${encodeURIComponent(researcherName)}`);
      } else {
        qc.setQueryData(resolveKey(researcherName, true), result);
        router.push(`/disambiguation?name=${encodeURIComponent(researcherName)}`);
      }
    } catch {
      setError(t("network_error"));
      setResolving(false);
    }
  }

  return (
    <>
      <Header />
      <main className="flex-1 py-4 px-4">
        <div className="max-w-4xl mx-auto" style={{ marginTop: "1rem" }}>

          {/* Hero */}
          <div className="text-center mb-6 relative">
            <div className="relative">
              <div
                className="flex justify-center items-center gap-3"
                style={{ marginBottom: 40, color: "#0066CC" }}
              >
                <Network className="w-12 h-12" strokeWidth={2} />
                <h1 className="text-5xl font-bold tracking-tight">Scholarmap</h1>
              </div>
              <div className="text-base text-gray-700 leading-relaxed max-w-3xl mx-auto space-y-4 text-left">
                {["landing_intro_1", "landing_intro_2", "landing_intro_3", "landing_intro_4"].map((key) => (
                  // Les traductions contiennent du balisage <strong> volontaire
                  <p key={key} dangerouslySetInnerHTML={{ __html: t(key) }} />
                ))}
              </div>
            </div>
          </div>

          {/* Search Form */}
          <div
            className="relative rounded-2xl overflow-hidden"
            style={{
              background: "linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%)",
              boxShadow: "0 8px 32px rgba(0, 102, 204, 0.12)",
              border: "1px solid rgba(20, 184, 166, 0.1)",
            }}
          >
            <div className="absolute top-0 right-0 w-32 h-32 opacity-5" style={{ background: "radial-gradient(circle at top right, #14B8A6 0%, transparent 70%)" }} />
            <div className="absolute bottom-0 left-0 w-32 h-32 opacity-5" style={{ background: "radial-gradient(circle at bottom left, #0066CC 0%, transparent 70%)" }} />

            <div className="relative p-10">
              <form onSubmit={handleSubmit} className="space-y-6">
                <div>
                  <label
                    htmlFor="researcher_name"
                    className="flex items-center space-x-2 text-sm font-semibold mb-3"
                    style={{ color: "#1E293B" }}
                  >
                    <svg className="w-5 h-5" style={{ color: "#0066CC" }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    <span>{t("landing_search_label")}</span>
                  </label>
                  <div className="relative">
                    <input
                      type="text"
                      id="researcher_name"
                      name="researcher_name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder={t("landing_search_placeholder")}
                      className="w-full px-5 py-4 rounded-xl text-gray-900 placeholder-gray-400 transition-all duration-200"
                      style={{ border: "2px solid rgba(0, 102, 204, 0.2)", background: "rgba(255, 255, 255, 0.9)" }}
                      onFocus={(e) => { e.target.style.borderColor = "#0066CC"; e.target.style.boxShadow = "0 0 0 4px rgba(0, 102, 204, 0.1)"; }}
                      onBlur={(e) => { e.target.style.borderColor = "rgba(0, 102, 204, 0.2)"; e.target.style.boxShadow = "none"; }}
                      required
                      autoFocus
                    />
                    <div className="absolute right-4 top-1/2 transform -translate-y-1/2 pointer-events-none">
                      <svg className="w-5 h-5 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                      </svg>
                    </div>
                  </div>
                </div>

                {error && (
                  <div
                    className="p-3 rounded-xl text-sm font-medium"
                    style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "#B91C1C" }}
                  >
                    {error}
                  </div>
                )}

                <div>
                  <button
                    type="submit"
                    disabled={resolving}
                    className="w-full px-8 py-4 rounded-xl font-semibold text-white text-lg transition-all duration-200 shadow-lg hover:shadow-xl hover:-translate-y-0.5 disabled:opacity-70 disabled:cursor-not-allowed disabled:hover:translate-y-0"
                    style={{ background: "linear-gradient(135deg, #0066CC, #0052A3)" }}
                  >
                    {resolving ? t("landing_submitting") : t("landing_submit")}
                  </button>
                </div>
              </form>

              {/* Info card */}
              <div className="mt-8">
                <div className="p-4 rounded-xl" style={{ background: "linear-gradient(135deg, #EFF6FF, #DBEAFE)", border: "1px solid rgba(0, 102, 204, 0.1)" }}>
                  <div className="flex items-start space-x-3">
                    <div className="flex-shrink-0 mt-0.5">
                      <svg className="w-5 h-5" style={{ color: "#0066CC" }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                    <div>
                      <p className="text-sm font-semibold mb-2" style={{ color: "#1E293B" }}>{t("landing_tips_title")}</p>
                      <ul className="text-sm text-gray-600 space-y-1.5">
                        <li>• {t("landing_tip_exact_name")}</li>
                        <li>• {t("landing_tip_openalex")}</li>
                        <li>• {t("landing_tip_duration")}</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Feature cards */}
          <div className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                color: "#0066CC",
                title: t("feature_network_title"),
                desc: t("feature_network_desc"),
                path: "M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z",
              },
              {
                color: "#0052A3",
                title: t("feature_patents_title"),
                desc: t("feature_patents_desc"),
                path: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
              },
              {
                color: "#1D4ED8",
                title: t("feature_impact_title"),
                desc: t("feature_impact_desc"),
                path: "M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z",
              },
            ].map(({ color, title, desc, path }) => (
              <div key={title} className="p-6 rounded-xl" style={{ background: "#ffffff", border: "1px solid #e2e8f0" }}>
                <svg className="w-8 h-8 mb-4" style={{ color }} fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d={path} />
                </svg>
                <h3 className="font-semibold mb-2" style={{ color: "#1E293B" }}>{title}</h3>
                <p className="text-sm" style={{ color: "#64748b", lineHeight: 1.6 }}>{desc}</p>
              </div>
            ))}
          </div>

          {/* Data sources */}
          <div className="mt-16 p-8 rounded-xl" style={{ background: "linear-gradient(135deg, #F0F9FF, #E0F2FE)", border: "2px solid #0066CC" }}>
            <div className="flex items-start space-x-4">
              <div className="flex-shrink-0 mt-1">
                <svg className="w-6 h-6" style={{ color: "#0066CC" }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold mb-3" style={{ color: "#1E293B" }}>{t("landing_sources_title")}</h3>
                <p className="text-sm mb-4" style={{ color: "#475569" }}>
                  {t("landing_sources_desc")}
                </p>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {[
                    { name: "OpenAlex", sub: t("source_openalex_sub"), color: "#0066CC" },
                    { name: "Google Patents", sub: t("source_patents_sub"), color: "#0052A3" },
                    { name: "ClinicalTrials", sub: t("source_trials_sub"), color: "#1D4ED8" },
                    { name: "Transparence Santé", sub: t("source_transparence_sub"), color: "#0369A1" },
                  ].map(({ name, sub, color }) => (
                    <div key={name} className="p-3 rounded-lg" style={{ background: "white", border: "1px solid #cbd5e1" }}>
                      <p className="font-medium text-sm" style={{ color }}>{name}</p>
                      <p className="text-xs" style={{ color: "#64748b" }}>{sub}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div style={{ height: 64 }} />
        </div>
      </main>
    </>
  );
}
