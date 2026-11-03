from .context_domains import DOMAIN_FIELDS
from .models import ContextItem, ContextPackage
from .context_sources import permitted, qualify, references_allowed, origin_refs
import re


class ContextHandler:
    def __init__(self, storage):
        self.storage = storage
        self.requests = []
        self.source_registry = None

    def load(self, request):
        self.requests.append(request)
        state = self.storage.load_state(request.project_id)
        package = ContextPackage(project_id=request.project_id, task_id=request.task_id)
        for domain in request.required_domains:
            items = self.storage.load_context(request.project_id, domain.value)
            aliases = {
                "FUNCTIONAL_PROCESS": "BUSINESS",
                "SAP_FUNCTIONAL": "SAP",
                "SAP_TECHNICAL": "SAP",
                "STANDARDS_GOVERNANCE": "ORGANIZATION",
            }
            if domain in aliases:
                items += self.storage.load_context(request.project_id, aliases[domain])
            # Project-local storage is not permission to use a cross-company item.
            project = self.storage.load_project(request.project_id)
            items = [
                item
                for item in items
                if permitted(item, project)
                and (
                    not item.adapter_id
                    or (
                        self.source_registry is not None
                        and item.adapter_id in self.source_registry.adapters
                        and self.source_registry.authorized(item.adapter_id, project, "local")
                    )
                )
            ]
            if domain in ("BUSINESS", "FUNCTIONAL_PROCESS") and state.requirement:
                items.append(
                    ContextItem(
                        content=state.requirement,
                        source="project:requirement",
                        source_type="user",
                        source_version=str(state.state_revision),
                    )
                )
            if domain == "SDLC":
                items.append(
                    ContextItem(content=state.model_dump_json(), source="project:state", source_type="state")
                )
            setattr(
                package,
                DOMAIN_FIELDS[domain.value],
                [qualify(item, domain, request.project_id) for item in items],
            )
        if "SDLC" in request.required_domains:
            memory = self.storage.load_memory(request.project_id)
            if memory.content and references_allowed(
                memory.source_refs, self.storage, project, self.source_registry, strict_versions=True
            ):
                package.sdlc_context.append(
                    qualify(
                        ContextItem(
                            content=memory.content[:2000],
                            source="project:memory",
                            source_type="memory",
                            evidence_status="inferred",
                            derivation_refs=memory.source_refs,
                        ),
                        "SDLC",
                        request.project_id,
                    )
                )
            session = self.storage.load_session(request.project_id)
            for index, message in list(enumerate(session.get("messages", [])))[-12:]:
                if message.get("role") == "user" and not re.match(
                    r"^(generate|approve|reject|status|go to|switch to|move to)\b",
                    message.get("content", ""),
                    re.I,
                ):
                    package.sdlc_context.append(
                        qualify(
                            ContextItem(
                                content=message["content"][:1200],
                                source=f"project:conversation:{index}",
                                source_type="conversation",
                            ),
                            "SDLC",
                            request.project_id,
                        )
                    )
        for artifact_id in request.upstream_artifacts:
            artifact = self.storage.load_artifact(request.project_id, artifact_id)
            package.upstream_artifacts.append(artifact.reference())
            if "SDLC" in request.required_domains:
                package.sdlc_context.append(
                    qualify(
                        ContextItem(
                            content=artifact.content,
                            source=f"artifact:{artifact.artifact_id}:v{artifact.artifact_version}",
                            source_type="artifact",
                            source_version=artifact.artifact_version,
                            approval_status=artifact.approval_status.value,
                            derivation_refs=origin_refs(artifact.evidence_provenance),
                        ),
                        "SDLC",
                        request.project_id,
                    )
                )
        return package
