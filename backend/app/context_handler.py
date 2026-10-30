from .local_storage import DOMAIN_FIELDS
from .models import ContextItem, ContextPackage


class ContextHandler:
    def __init__(self, storage):
        self.storage = storage
        self.requests = []

    def load(self, request):
        self.requests.append(request)
        state = self.storage.load_state(request.project_id)
        package = ContextPackage(project_id=request.project_id, task_id=request.task_id)
        for domain in request.required_domains:
            items = self.storage.load_context(request.project_id, domain.value)
            if domain == "BUSINESS" and state.requirement:
                items.append(
                    ContextItem(content=state.requirement, source="project:requirement", source_type="user")
                )
            if domain == "SDLC":
                items.append(
                    ContextItem(content=state.model_dump_json(), source="project:state", source_type="state")
                )
            setattr(package, DOMAIN_FIELDS[domain.value], items)
        for artifact_id in request.upstream_artifacts:
            artifact = self.storage.load_artifact(request.project_id, artifact_id)
            package.upstream_artifacts.append(artifact.reference())
            if "SDLC" in request.required_domains:
                package.sdlc_context.append(
                    ContextItem(
                        content=artifact.content,
                        source=f"artifact:{artifact.artifact_id}:v{artifact.artifact_version}",
                        source_type="artifact",
                    )
                )
                memory = self.storage.load_memory(request.project_id)
                if memory.content:
                    items.append(
                        ContextItem(
                            content=memory.content[:2000], source="project:memory", source_type="memory"
                        )
                    )
        return package
