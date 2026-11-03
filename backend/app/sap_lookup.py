from .models import CapabilityResponse
from .context_sources import permitted, qualify, evidence_id


class CuratedSAPLookup:
    def __init__(self, storage, sources=None):
        self.storage = storage
        self.sources = sources

    def invoke(self, request):
        query = request.inputs.get("query", "").lower()
        project = self.storage.load_project(request.project_id)
        items = [
            qualify(item, domain, request.project_id)
            for domain in ("SAP", "SAP_FUNCTIONAL", "SAP_TECHNICAL")
            for item in self.storage.load_context(request.project_id, domain)
        ]
        matches = {
            evidence_id(item): item.model_dump(mode="json")
            for item in items
            if permitted(item, project)
            and (not item.adapter_id or self.sources and self.sources.authorized(item.adapter_id, project))
            and (not query or query in item.content.lower())
        }
        return CapabilityResponse(
            task_id=request.task_id,
            capability_id=request.capability_id,
            status="success",
            output={"items": [matches[key] for key in sorted(matches)], "source": "project-curated-only"},
        )
