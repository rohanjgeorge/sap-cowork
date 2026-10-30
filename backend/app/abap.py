"""Replaceable V1 ABAP capability. Deliberately returns demonstration code only."""

from .models import Artifact, CapabilityResponse


class ABAPStub:
    def __init__(self):
        self.invocations = []

    def invoke(self, request):
        self.invocations.append(request)
        versions = [
            int(r.version.split(".")[0]) for r in request.state.artifact_registry if r.artifact_type == "ABAP"
        ]
        version = str(max(versions, default=0) + 1)
        tdd = [r for r in request.context.upstream_artifacts if r.artifact_type == "TDD"]
        source = (
            f"TDD v{tdd[0].version} ({tdd[0].approval_status})"
            if tdd
            else "Available requirements/context; TDD missing"
        )
        content = (
            "* SAP CoWork V1 demonstration stub. NOT production ABAP.\n"
            f"* Input: {source}\n"
            "* Replace this capability with the ABAP workstream implementation.\n"
            "REPORT zcowork_sto_demo.\n"
            "PARAMETERS p_plant TYPE c LENGTH 4 DEFAULT '1000'.\n"
            "START-OF-SELECTION.\n"
            "  WRITE: / 'STO automation stub for plant', p_plant.\n"
            "* TODO: Implement reviewed delivery creation and failure reporting.\n"
        )
        artifact = Artifact(
            artifact_id="ABAP",
            project_id=request.project_id,
            artifact_type="ABAP",
            content=content,
            artifact_version=version,
            template_version="abap-stub-1.0",
            source_task_id=request.task_id,
            edited_by="local",
            sources=[f"artifact:{r.artifact_id}:v{r.version}" for r in request.context.upstream_artifacts],
        )
        return CapabilityResponse(
            task_id=request.task_id,
            capability_id=request.capability_id,
            status="success",
            output={"artifact": artifact.model_dump(mode="json"), "implementation": "abap-stub-v1"},
        )
