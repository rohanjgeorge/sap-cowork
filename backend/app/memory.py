from .models import ProjectMemory, now
from .context_sources import permitted, qualify, origin_refs


class MemoryService:
    """Rebuild compact semantic summaries from durable project evidence, never the reverse."""

    def __init__(self, storage):
        self.storage = storage

    def refresh(self, state):
        project = self.storage.load_project(state.project_id)
        referenced = []

        def facts(domain):
            aliases = {
                "BUSINESS": ["BUSINESS", "FUNCTIONAL_PROCESS"],
                "SAP": ["SAP", "SAP_FUNCTIONAL", "SAP_TECHNICAL"],
                "ORGANIZATION": ["ORGANIZATION", "STANDARDS_GOVERNANCE"],
            }
            entries = [
                qualify(item, name, state.project_id)
                for name in aliases.get(domain, [domain])
                for item in self.storage.load_context(state.project_id, name)
                if permitted(item, project)
            ]
            referenced.extend(entries[-12:])
            return "\n".join(f"- {item.content[:700]}" for item in entries[-12:]) or "No curated facts yet."

        decisions = "\n".join(f"- {d.description}" for d in state.decisions) or "None recorded."
        resolved = (
            "\n".join(
                f"- {c.question} {c.response}" for c in state.open_clarifications if c.status == "resolved"
            )
            or "None yet."
        )
        sections = [
            ("# Project Summary", ""),
            ("## Objective", state.requirement[:2500] or "Requirement not supplied."),
            ("## Key Business Facts", facts("BUSINESS")),
            ("## Key SAP Facts", facts("SAP")),
            ("## Organization Specific Facts", facts("ORGANIZATION")),
            ("## Historical Development Findings", facts("HISTORICAL_DEVELOPMENT")),
            ("## Decisions and Assumptions", decisions),
            ("## Resolved Clarifications", resolved),
            (
                "## Current Status",
                f"{state.current_stage}; {state.task_status}. "
                f"Next: {state.recommended_next_action}. "
                f"Artifacts: {', '.join(f'{r.artifact_type} v{r.version} {r.approval_status}' for r in state.artifact_registry)}",
            ),
        ]
        memory = ProjectMemory(
            project_id=state.project_id,
            content="\n\n".join(f"{heading}\n{body}" for heading, body in sections),
            source_refs=origin_refs(referenced),
        )
        self.storage.save_memory(state.project_id, memory)
        project = self.storage.load_project(state.project_id)
        project.updated_at = now()
        self.storage.save_project(project)
        return memory
