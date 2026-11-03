export const STAGES = [
  "Planning",
  "Analysis",
  "Design",
  "Development",
  "Testing",
] as const;
export type Stage = (typeof STAGES)[number];
export type Approval = "draft" | "pending_approval" | "approved" | "rejected";
export type ArtifactRef = {
  artifact_id: string;
  artifact_type: string;
  version: string;
  approval_status: Approval;
};
export type Artifact = {
  artifact_id: string;
  project_id: string;
  artifact_type: string;
  artifact_version: string;
  content: string;
  approval_status: Approval;
  template_version: string;
  created_date: string;
  last_edited_date: string;
  edited_by: string | null;
  approved_by: string | null;
  feedback: string | null;
  sources: string[];
  template_ref?: string | null;
  recommendations?: string[];
  context_package_ref?: string | null;
  context_plan_ref?: string | null;
  context_gaps?: ContextGap[];
  evidence_provenance?: EvidenceSource[];
};
export type Clarification = {
  resolution?: string | null;
  task_id?: string | null;
  clarification_id: string;
  question: string;
  status: string;
  response: string | null;
};
export type Decision = {
  decision_id: string;
  description: string;
  decided_by?: string;
};
export type ProjectFlag = {
  flag_id: string;
  description: string;
  type?: "warning" | "blocker" | "exception";
  status?: "active" | "resolved";
};
export type ProjectRecords = {
  clarifications?: Clarification[];
  open_clarifications?: Clarification[];
  decisions?: Decision[];
  flags?: ProjectFlag[];
};
export type Issue = {
  code: string;
  message: string;
  severity: "info" | "warning" | "error";
  blocking: boolean;
  stage: Stage;
};
export type StageStatus = {
  stage: Stage;
  color: "green" | "amber" | "grey";
  label: string;
  expected_artifact: string;
  expected_artifacts?: string[];
  documents: ArtifactRef[];
  clarifications: Clarification[];
  issues: Issue[];
};
export type ProjectStatus = {
  current_stage: Stage;
  current_task: string | null;
  task_status: string;
  recommended_stage: Stage | null;
  recommended_next_action: string | null;
  stages: StageStatus[];
  issues: Issue[];
  open_clarifications: Clarification[];
  current_draft_stage?: Stage;
  current_approved_stage?: Stage;
  project_status?: "active" | "completed" | "incomplete";
  state_revision?: number;
  follow_ups?: Record<string, string>;
  flags?: ProjectFlag[];
  confirmations?: { kind: string; active: boolean }[];
};
export type Project = {
  client_name?: string | null;
  organization_id?: string | null;
  program_id?: string | null;
  sap_applicability?: Record<string, string>;
  project_id: string;
  project_name: string;
  description: string;
  created_at: string;
  updated_at: string;
};
export type ProjectSummary = Project & { status: ProjectStatus };
export type ContextStatus = {
  used_tokens: number;
  usable_context: number;
  model_context_window: number;
  usage_percent: number;
  band: string;
  estimated: boolean;
  active_domains: string[];
  compactions: number;
  provider: string;
  model: string;
  planning?: {
    package_ref: string;
    plan_ref: string;
    gaps: ContextGap[];
    constraints: Record<string, unknown>;
  } | null;
};
export type ContextGap = {
  requirement_id: string;
  gap_type: string;
  impact: string;
  reason: string;
  qualification: string;
  follow_up: string;
};
export type EvidenceSource = {
  source_id?: string;
  source?: string;
  original_uri?: string;
  source_version?: string | null;
  source_category?: string;
  domain?: string;
  scope?: string;
  evidence_status?: string;
  authority?: string;
  rights?: string;
};
export type Message = {
  role: string;
  content: string;
  origin?: "model" | "workflow";
  provider?: string;
  model?: string;
};
export type Asset = {
  kind: string;
  file_id?: string;
  name?: string;
  artifact_id?: string;
  artifact_type?: string;
  version?: string;
  approval_status?: Approval;
  size?: number;
};
export type Workspace = {
  snapshot_at?: string;
  onboarding?: {
    artifact_statuses?: Record<string, "draft" | "approved">;
    selected_artifacts: string[];
    pending_artifacts: string[];
    complete: boolean;
    message: string;
  } | null;
  project: Project;
  state: {
    clarifications?: Clarification[];
    decisions?: Decision[];
    flags?: ProjectFlag[];
    project_id: string;
    current_stage: Stage;
    current_draft_stage?: Stage;
    current_approved_stage?: Stage;
    project_status?: "active" | "completed" | "incomplete";
    state_revision?: number;
    current_task: string | null;
    expected_next_artifact: string | null;
    task_status: string;
    active_task_id: string | null;
    requirement: string;
    artifact_registry: ArtifactRef[];
    open_clarifications: Clarification[];
  };
  status: ProjectStatus;
  memory: { content: string };
  session: { messages: Message[]; compaction_notice?: string };
  context: ContextStatus;
  assets: Asset[];
};
export type ChatInput = {
  message?: string;
  action?: string;
  artifact_type?: string;
  task_id?: string;
  clarification_id?: string;
  version?: string;
  feedback?: string;
  stage?: Stage;
  new_version?: boolean;
  authors?: string;
  remarks?: string;
  expected_revision?: number;
  request_id?: string;
};
export type ChatResult = {
  message: string;
  workspace: Workspace;
  artifact?: Artifact;
  questions?: string[];
  error?: string;
};
