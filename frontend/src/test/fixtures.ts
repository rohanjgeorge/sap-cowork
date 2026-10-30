import type { Workspace } from "../types";
export function workspace(): Workspace {
  return {
    project: {
      project_id: "p",
      project_name: "STO Automation",
      description: "",
      created_at: "2026-10-30T00:00:00Z",
      updated_at: "2026-10-30T00:00:00Z",
    },
    state: {
      project_id: "p",
      current_stage: "Planning",
      current_task: null,
      expected_next_artifact: "BRD",
      task_status: "idle",
      active_task_id: null,
      requirement: "STO CR",
      artifact_registry: [],
      open_clarifications: [],
    },
    status: {
      current_stage: "Planning",
      current_task: null,
      task_status: "idle",
      recommended_stage: null,
      recommended_next_action: "Generate BRD",
      stages: ["Planning", "Analysis", "Design", "Development", "Testing"].map(
        (stage, i) => ({
          stage: stage as Workspace["status"]["current_stage"],
          color: i === 0 ? "amber" : "grey",
          label: i === 0 ? "In progress / attention" : "Yet to start",
          expected_artifact: ["BRD", "FRD", "TDD", "ABAP", "UAT"][i],
          documents: [],
          clarifications: [],
          issues: [],
        }),
      ),
      issues: [],
      open_clarifications: [],
    },
    memory: { content: "# Project Summary" },
    session: { messages: [] },
    context: {
      used_tokens: 0,
      usable_context: 26304,
      model_context_window: 32000,
      usage_percent: 0,
      band: "healthy",
      estimated: true,
      active_domains: [],
      compactions: 0,
      provider: "fake",
      model: "deterministic-v1",
    },
    assets: [],
  };
}
