"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchTaskInfo } from "@/lib/analyze";
import { useT } from "@/lib/i18n";
import { CenteredSpinner, EmptyState } from "@/components/shared/empty-state";
import { usePolling } from "@/hooks/usePolling";
import { NetworkAnimation } from "./network-animation";
import { TipsCarousel } from "./tips-carousel";
import styles from "./loading.module.css";

/** The five pipeline stages, in the order the progress bar lights them up. */
const STEP_KEYS = [
  "loading_step_publications",
  "loading_step_patents",
  "loading_step_clinical",
  "loading_step_transparence",
  "loading_step_graph",
];

/** Progress thresholds at which each pipeline step lights up. */
function activeStep(progress: number): number {
  if (progress >= 85) return 4;
  if (progress >= 70) return 3;
  if (progress >= 50) return 2;
  if (progress >= 25) return 1;
  return 0;
}

export default function AnalyzeLoadingPage() {
  const params = useParams();
  const router = useRouter();
  const t = useT();
  const taskId = Array.isArray(params.taskId) ? params.taskId[0] : (params.taskId ?? null);

  const [tipsDone, setTipsDone] = useState(false);

  const { data: task, isLoading, isError } = useQuery({
    queryKey: ["analyze", "task", taskId],
    queryFn: () => fetchTaskInfo(taskId!),
    enabled: !!taskId,
    retry: false,
    staleTime: Infinity,
  });

  const { progress, message, isComplete, error } = usePolling({ taskId });

  const researcherName = task?.researcher_name ?? "";
  const isOnboarding = task?.is_onboarding ?? false;

  // New users see every tip before landing on the report
  useEffect(() => {
    if (!isComplete || !researcherName) return;
    if (isOnboarding && !tipsDone) return;
    const t = setTimeout(() => {
      window.location.href = `/report/${encodeURIComponent(researcherName)}`;
    }, 1200);
    return () => clearTimeout(t);
  }, [isComplete, isOnboarding, tipsDone, researcherName]);

  if (isLoading) return <CenteredSpinner />;
  if (isError || !task) return <EmptyState message={t("loading_task_expired")} />;

  const current = activeStep(progress);

  return (
    <div className="flex-1 flex flex-col w-full pt-6">
      {/* Title */}
      <div className="text-center mb-4">
        <p className="text-base font-medium" style={{ color: "#334155", letterSpacing: "0.01em" }}>
          {t("loading_building_network")}
        </p>
        <h2 className="mt-1 text-3xl font-bold" style={{ color: "#1E293B" }}>
          {researcherName}
        </h2>
      </div>

      <NetworkAnimation />

      {isOnboarding && <TipsCarousel onAllShown={() => setTipsDone(true)} />}

      {/* Status */}
      <div className="max-w-[700px] mx-auto w-full px-4 mb-5">
        <div className={styles.steps}>
          {STEP_KEYS.map((key, i) => (
            <div
              key={key}
              className={`${styles.step} ${
                i < current ? styles.stepDone : i === current ? styles.stepActive : ""
              }`}
            >
              {t(key)}
            </div>
          ))}
        </div>

        <div className={styles.progressTrack}>
          <div className={styles.progressFill} style={{ width: `${progress}%` }} />
        </div>

        <div
          className="text-center text-[13px] min-h-5"
          style={{ color: error ? "#ef4444" : "#64748B" }}
        >
          {error ?? message}
        </div>
      </div>

      {/* Retry — only once the pipeline has actually failed */}
      {error && (
        <div className="text-center mb-6">
          <button
            type="button"
            onClick={() =>
              router.push(`/disambiguation?name=${encodeURIComponent(researcherName)}`)
            }
            className="px-7 py-2.5 rounded-lg text-sm font-semibold text-white transition-colors"
            style={{ background: "#2D7FF9" }}
          >
            {t("loading_retry_button")}
          </button>
          <p className="text-xs mt-2" style={{ color: "#94A3B8" }}>
            {t("loading_retry_hint")}
          </p>
        </div>
      )}
    </div>
  );
}
