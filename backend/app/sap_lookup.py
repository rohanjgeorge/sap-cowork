from .models import CapabilityResponse


class CuratedSAPLookup:
    def __init__(self, storage):
        self.storage = storage

    def invoke(self, request):
        query = request.inputs.get("query", "").lower()
        items = self.storage.load_context(request.project_id, "SAP")
        matches = [item.model_dump() for item in items if not query or query in item.content.lower()]
        return CapabilityResponse(
            task_id=request.task_id,
            capability_id=request.capability_id,
            status="success",
            output={"items": matches, "source": "project-curated-only"},
        )
