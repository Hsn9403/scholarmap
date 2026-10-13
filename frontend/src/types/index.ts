import { z } from "zod";

// ── Task / Pipeline ───────────────────────────────────────────────────────────
export const TaskStatusSchema = z.object({
  status: z.enum(["pending", "processing", "analyzing", "completed", "error"]),
  progress: z.number().min(0).max(100).optional(),
  message: z.string().optional(),
  researcher_name: z.string().optional(),
});
export type TaskStatus = z.infer<typeof TaskStatusSchema>;

// ── Disambiguation ────────────────────────────────────────────────────────────
export const OACandidateSchema = z.object({
  openalex_id: z.string(),
  name: z.string(),
  works_count: z.number(),
  cited_by_count: z.number(),
  affiliations: z.array(z.string()),
  all_affiliations: z.array(z.string()),
});
export type OACandidate = z.infer<typeof OACandidateSchema>;

// ── Analyze funnel ────────────────────────────────────────────────────────────
export const ExistingReportSchema = z.object({
  name: z.string(),
  affiliation: z.string().nullable(),
  h_index: z.number().nullable(),
  created_at: z.string().nullable(),
});
export type ExistingReport = z.infer<typeof ExistingReportSchema>;

/** What /api/analyze/resolve decided to do with a researcher name. */
export const ResolveResultSchema = z.discriminatedUnion("action", [
  z.object({
    action: z.literal("reuse"),
    researcher_name: z.string(),
    existing: ExistingReportSchema,
    scholar_id: z.string().nullable().optional(),
    openalex_id: z.string().nullable().optional(),
  }),
  z.object({
    action: z.literal("disambiguate"),
    researcher_name: z.string(),
    candidates: z.array(OACandidateSchema),
  }),
  z.object({
    action: z.literal("error"),
    error: z.string(),
  }),
]);
export type ResolveResult = z.infer<typeof ResolveResultSchema>;

export const StartResultSchema = z.object({
  task_id: z.string(),
  researcher_name: z.string(),
});
export type StartResult = z.infer<typeof StartResultSchema>;

export const TaskInfoSchema = z.object({
  task_id: z.string(),
  researcher_name: z.string(),
  is_openalex: z.boolean(),
  is_onboarding: z.boolean(),
  use_celery: z.boolean(),
});
export type TaskInfo = z.infer<typeof TaskInfoSchema>;

// ── Report ────────────────────────────────────────────────────────────────────
/** GPT contextualisation of the H-index. Fields are best-effort, hence all optional. */
export const HIndexAssessmentSchema = z.object({
  percentile: z.number().nullish(),
  field: z.string().nullish(),
  scale: z.string().nullish(),
  category: z.string().nullish(),
  investment_signal: z.string().nullish(),
});
export type HIndexAssessment = z.infer<typeof HIndexAssessmentSchema>;

export const PatentSchema = z.object({
  id: z.string().nullish(),
  label: z.string(),
  url: z.string().nullish(),
});
export type Patent = z.infer<typeof PatentSchema>;

export const ReportResearcherSchema = z.object({
  name: z.string(),
  affiliation: z.string().nullish(),
  h_index: z.number().nullish(),
  h_index_percentile: z.number().nullish(),
  h_index_ai_assessment: HIndexAssessmentSchema.nullish(),
  patents_count: z.number().default(0),
  patents: z.array(PatentSchema).default([]),
  recent_publications: z.number().default(0),
  scholar_id: z.string().nullish(),
  openalex_id: z.string().nullish(),
  citations: z.number().default(0),
  specialty_tags: z.array(z.string()).default([]),
});
export type ReportResearcher = z.infer<typeof ReportResearcherSchema>;

export const ReportDataSchema = z.object({
  researcher: ReportResearcherSchema,
  graph_url: z.string().nullish(),
  excel_url: z.string().nullish(),
});
export type ReportData = z.infer<typeof ReportDataSchema>;

export const ExcelReadySchema = z.object({
  ready: z.boolean(),
  url: z.string(),
});

// ── Coauthor profile ─────────────────────────────────────────────────────────
export const CoauthorPatentSchema = z.object({
  title: z.string().default(""),
  patent_id: z.string().nullish(),
  assignee: z.string().nullish(),
  link: z.string().nullish(),
});
export type CoauthorPatent = z.infer<typeof CoauthorPatentSchema>;

const LabelledEntitySchema = z.object({ label: z.string() });

export const CoauthorProfileSchema = z.object({
  name: z.string(),
  affiliation: z.string().nullish(),
  h_index: z.number().nullish(),
  openalex_id: z.string().nullish(),
  scholar_id: z.string().nullish(),
  collaborations_with_seed: z.number().default(0),
  is_seed: z.boolean().default(false),
  publications_count: z.number().default(0),
  patents_count: z.number().default(0),
  patents: z.array(CoauthorPatentSchema).default([]),
  connected_corporates: z.array(LabelledEntitySchema).default([]),
  connected_institutions: z.array(LabelledEntitySchema).default([]),
  /** Comma-separated on the wire — the service returns a raw GPT string. */
  specialty_tags: z.string().nullish(),
});
export type CoauthorProfile = z.infer<typeof CoauthorProfileSchema>;

export const CoauthorResponseSchema = z.object({
  coauthor: CoauthorProfileSchema,
  seed_researcher: z.string().nullish(),
});
