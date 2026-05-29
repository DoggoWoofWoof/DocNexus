export type ArtifactType = "pptx" | "xlsx" | "docx" | "markdown" | "chart_png" | "chart_svg";

export type ArtifactRef = {
  id: string;
  type: ArtifactType;
  filename: string;
  mimeType: string;
  downloadUrl: string;
  sourceAgent: string;
};

export type TraceEvent = {
  id: string;
  agent: "orchestrator" | "data" | "ppt" | "excel" | "report" | "sandbox" | "judge";
  status: "started" | "completed" | "failed" | "retrying" | "skipped";
  message: string;
  timestamp: string;
  elapsedMs?: number | null;
  metadata: Record<string, unknown>;
};

export type SandboxOutput = {
  code: string;
  stdout: string;
  stderr: string;
  chartArtifactId?: string | null;
  executionStatus: "completed" | "failed";
};

export type JudgeDecision = {
  status: "approved" | "needs_revision" | "failed_after_retry";
  reason: string;
  targetAgent?: string | null;
  revisionInstructions?: string | null;
};

export type QueryResponse = {
  requestId: string;
  query: string;
  answerMarkdown?: string | null;
  artifacts: ArtifactRef[];
  sandboxOutput?: SandboxOutput | null;
  trace: TraceEvent[];
  judgeDecision?: JudgeDecision | null;
  metadata: Record<string, unknown>;
};

export type QueryStreamEvent =
  | { type: "trace"; data: TraceEvent }
  | { type: "result"; data: QueryResponse }
  | { type: "error"; data: { message: string } };

export type QueryPreferences = {
  icd10Codes: string[];
  states: string[];
  regions: string[];
  specialties: string[];
  volumeThreshold?: "low" | "high" | "very_high" | null;
  boardCertified?: boolean | null;
};

export type QueryRequest = {
  query: string;
  preferences: QueryPreferences;
  requestedArtifacts: ArtifactType[];
  includeTrace: boolean;
};

export type Physician = {
  id: string;
  npi: string;
  firstName: string;
  lastName: string;
  specialty: string;
  affiliation: string;
  city: string;
  state: string;
  icd10ClaimVolume: Record<string, number>;
  totalNSCLCClaims: number;
  volumeTier: "low" | "high" | "very_high";
  email: string;
  boardCertified: boolean;
};

export type PhysicianListResponse = {
  count: number;
  physicians: Physician[];
};
