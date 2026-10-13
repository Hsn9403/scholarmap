"use client";

import { Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { fetcher } from "@/lib/fetcher";
import { useT } from "@/lib/i18n";
import { CoauthorResponseSchema, type CoauthorProfile } from "@/types";

/**
 * Standalone co-author card. Opened in a new tab from the graph, so it carries no
 * app chrome and its back action closes the tab rather than navigating.
 */
export default function CoauthorPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <CoauthorContent />
    </Suspense>
  );
}

function CoauthorContent() {
  const params = useParams();
  const searchParams = useSearchParams();
  const t = useT();

  const rawName = Array.isArray(params.name) ? params.name[0] : (params.name ?? "");
  const name = decodeURIComponent(rawName);
  const seed = searchParams.get("seed");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["coauthor", name, seed],
    queryFn: async () => {
      const url = `/api/coauthor/${encodeURIComponent(name)}${
        seed ? `?seed=${encodeURIComponent(seed)}` : ""
      }`;
      return CoauthorResponseSchema.parse(await fetcher<unknown>(url));
    },
    enabled: !!name,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <div className="min-h-screen" style={{ background: "#FAFBFC" }}>
      <div className="max-w-[920px] mx-auto px-6 py-8">
        <button
          type="button"
          onClick={() => window.close()}
          className="inline-flex items-center gap-2 px-3 py-2 mb-8 rounded-md text-sm font-medium transition-colors hover:bg-gray-200"
          style={{ color: "#6B7280" }}
        >
          <ArrowLeft className="w-4 h-4" />
          {t("back")}
        </button>

        {isLoading ? (
          <Spinner />
        ) : isError || !data ? (
          <div className="rounded-xl bg-white p-8 text-center text-sm" style={{ color: "#9CA3AF" }}>
            {t("coauthor_not_available")}
          </div>
        ) : (
          <ProfileCard profile={data.coauthor} seed={data.seed_researcher ?? seed} />
        )}
      </div>
    </div>
  );
}

function ProfileCard({
  profile,
  seed,
}: {
  profile: CoauthorProfile;
  seed?: string | null;
}) {
  const t = useT();

  // The service returns GPT's raw comma-separated string
  const tags = (profile.specialty_tags ?? "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  return (
    <div
      className="bg-white rounded-xl overflow-hidden"
      style={{ boxShadow: "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)" }}
    >
      {/* Header */}
      <div
        className="px-8 py-10 flex flex-col md:flex-row md:justify-between md:items-start gap-4"
        style={{ borderBottom: "1px solid #E5E7EB" }}
      >
        <div className="flex-1">
          <h1 className="text-3xl font-bold mb-2" style={{ color: "#1F2937" }}>
            {profile.name}
          </h1>
          {profile.affiliation && (
            <div className="text-[15px] mb-5" style={{ color: "#6B7280" }}>
              {profile.affiliation}
            </div>
          )}
          <div className="flex gap-6 flex-wrap">
            <Meta label={t("metric_hindex")} value={profile.h_index ?? "—"} />
          </div>
        </div>

        {tags.length > 0 && (
          <div className="flex gap-2 flex-wrap md:mt-5">
            {tags.map((tag) => (
              <span
                key={tag}
                className="inline-block px-3 py-1.5 rounded-md text-xs font-semibold"
                style={{ background: "#F0F9FF", color: "#0369A1", border: "1px solid #BAE6FD" }}
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Stats */}
      <div
        className="grid gap-5 p-8"
        style={{
          gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
          borderBottom: "1px solid #E5E7EB",
        }}
      >
        {profile.is_seed ? (
          <Stat value={profile.publications_count} label={t("coauthor_publications")} />
        ) : (
          <Stat
            value={profile.collaborations_with_seed}
            label={t("coauthor_copublications", { name: seed ?? "seed" })}
            small
          />
        )}
        <Stat value={profile.patents_count} label={t("metric_patents")} />
        <Stat value={profile.connected_corporates.length} label={t("coauthor_companies")} />
        <Stat value={profile.connected_institutions.length} label={t("coauthor_institutions")} />
      </div>

      {/* Sections */}
      <div className="p-8 space-y-10">
        {profile.patents.length > 0 && (
          <Section title={`${t("metric_patents")} (${profile.patents.length})`}>
            <ul className="space-y-3">
              {profile.patents.map((p, i) => (
                <li
                  key={p.patent_id ?? `${p.title}-${i}`}
                  className="p-4 rounded-lg bg-white transition-shadow hover:shadow-sm"
                  style={{ border: "1px solid #E5E7EB" }}
                >
                  <div className="font-semibold text-[15px] mb-1.5" style={{ color: "#1F2937" }}>
                    {p.title}
                  </div>
                  {p.patent_id && (
                    <div className="text-xs mb-2 font-mono" style={{ color: "#9CA3AF" }}>
                      {p.patent_id}
                    </div>
                  )}
                  {p.assignee && (
                    <div className="text-[13px] mb-2.5" style={{ color: "#6B7280" }}>
                      {t("coauthor_patent_assignee")}: {p.assignee}
                    </div>
                  )}
                  {p.link && (
                    <a
                      href={p.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block text-[13px] font-medium hover:underline"
                      style={{ color: "#0066CC" }}
                    >
                      {t("coauthor_patent_link")}
                    </a>
                  )}
                </li>
              ))}
            </ul>
          </Section>
        )}

        {profile.connected_corporates.length > 0 && (
          <Section title={`${t("coauthor_companies")} (${profile.connected_corporates.length})`}>
            <div className="flex flex-wrap gap-2">
              {profile.connected_corporates.map((c) => (
                <span
                  key={c.label}
                  className="px-3 py-1.5 rounded-md text-[13px] font-medium"
                  style={{ background: "#E0F2FE", color: "#0369A1" }}
                >
                  {c.label}
                </span>
              ))}
            </div>
          </Section>
        )}

        {profile.connected_institutions.length > 0 && (
          <Section
            title={`${t("coauthor_institutions")} (${profile.connected_institutions.length})`}
          >
            <div
              className="grid gap-3"
              style={{ gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}
            >
              {[...profile.connected_institutions]
                .sort((a, b) => a.label.localeCompare(b.label))
                .map((inst) => (
                  <div
                    key={inst.label}
                    className="px-4 py-3.5 rounded-lg transition-all hover:-translate-y-0.5"
                    style={{
                      background:
                        "linear-gradient(135deg, rgba(13,148,136,0.08) 0%, rgba(14,165,233,0.06) 100%)",
                      border: "1px solid rgba(13,148,136,0.15)",
                    }}
                  >
                    <span
                      className="block text-sm font-medium break-words leading-snug"
                      style={{ color: "#1F2937" }}
                    >
                      {inst.label}
                    </span>
                  </div>
                ))}
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <div
        className="text-xs font-semibold uppercase"
        style={{ color: "#9CA3AF", letterSpacing: "0.05em" }}
      >
        {label}
      </div>
      <div className="text-xl font-bold" style={{ color: "#14B8A6" }}>
        {value}
      </div>
    </div>
  );
}

function Stat({
  value,
  label,
  small,
}: {
  value: number;
  label: string;
  small?: boolean;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="text-[28px] font-bold leading-none" style={{ color: "#1F2937" }}>
        {value}
      </div>
      <div
        className="font-medium uppercase"
        style={{ color: "#6B7280", letterSpacing: "0.05em", fontSize: small ? 10 : 12 }}
      >
        {label}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div
        className="text-sm font-semibold uppercase mb-4 pb-3"
        style={{ color: "#0066CC", letterSpacing: "0.06em", borderBottom: "2px solid #F3F4F6" }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

function Spinner() {
  return (
    <div className="flex items-center justify-center py-24">
      <div
        className="w-10 h-10 rounded-full animate-spin"
        style={{ border: "3px solid #E5E7EB", borderTopColor: "#14B8A6" }}
      />
    </div>
  );
}
