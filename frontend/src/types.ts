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
};
export type Clarification = {
  clarification_id: string;
  question: string;
  status: string;
  response: string | null;
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
};
export type Project = {
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
  project: Project;
  state: {
    project_id: string;
    current_stage: Stage;
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
};
export type ChatResult = {
  message: string;
  workspace: Workspace;
  artifact?: Artifact;
  questions?: string[];
  error?: string;
};
