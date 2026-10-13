import { api } from "@/lib/fetcher";
import {
  ResolveResultSchema,
  StartResultSchema,
  TaskInfoSchema,
  type ResolveResult,
  type StartResult,
  type TaskInfo,
} from "@/types";

/** React Query key for a resolve call — shared so the landing page can seed the cache. */
export function resolveKey(researcherName: string, forceNew = false) {
  return ["analyze", "resolve", researcherName, forceNew] as const;
}

/**
 * Ask the backend what to do with a researcher name. Never starts the pipeline:
 * either an existing report can be reused, or a profile must be picked.
 */
export async function resolveAnalysis(
  researcherName: string,
  forceNew = false
): Promise<ResolveResult> {
  const { data } = await api.post("/api/analyze/resolve", {
    researcher_name: researcherName,
    force_new: forceNew,
  });
  const parsed = ResolveResultSchema.safeParse(data);
  if (!parsed.success) {
    return { action: "error", error: "Réponse inattendue du serveur." };
  }
  return parsed.data;
}

/** Start the discovery pipeline for a disambiguated profile. */
export async function startAnalysis(params: {
  researcherName: string;
  openalexId?: string | null;
  scholarId?: string | null;
  forceNew?: boolean;
}): Promise<StartResult> {
  const { data } = await api.post("/api/analyze/start", {
    researcher_name: params.researcherName,
    openalex_id: params.openalexId ?? null,
    scholar_id: params.scholarId ?? null,
    force_new: params.forceNew ?? false,
  });
  return StartResultSchema.parse(data);
}

/** Task metadata (researcher name, onboarding flag) for the loading page. */
export async function fetchTaskInfo(taskId: string): Promise<TaskInfo> {
  const { data } = await api.get(`/api/analyze/task/${taskId}`);
  return TaskInfoSchema.parse(data);
}

/** Short OpenAlex id (A5023888391) out of a full URL. */
export function shortOpenAlexId(openalexId: string): string {
  return openalexId.split("/").pop() ?? openalexId;
}
