from backend.app.context_sources import KnowledgeCopies, permitted, qualify
from backend.app.models import ContextItem, Project, ProjectState
from backend.app.context_planner import ContextPlanner


def test_profiles_are_versioned_and_dynamic_needs_cannot_remove_fixed_needs():
    version, needs = ContextPlanner().requirements(ProjectState(project_id="p"), "TDD")
    assert version == "1.0"
    assert {n.requirement_id for n in needs} >= {
        "artifact.frd",
        "sap.release",
        "sap.technical",
        "application.template",
    }
    assert all(not n.material for n in needs)


def test_scope_permissions_and_claim_metadata_are_independent():
    project = Project(project_id="p", project_name="CR", organization_id="ABC", tenant_id="A")
    item = qualify(
        ContextItem(content="Example API", source="sap.md", source_type="curated", domain="SAP_TECHNICAL"),
        "SAP_TECHNICAL",
        "p",
    )
    assert item.source_category == "SRC-05" and item.authority == "unverified"
    assert item.original_uri == "sap.md" and item.evidence_status == "unknown"
    assert not permitted(item.model_copy(update={"tenant_id": "B"}), project)
    assert not permitted(item.model_copy(update={"allowed_users": ["someone_else"]}), project)
    assert not permitted(item.model_copy(update={"scope": "global", "confidential": True}), project)


def test_copy_reconciliation_preserves_material_changes_and_enforces_revocations(storage):
    project = storage.load_project("p")
    project.organization_id = "ABC"
    storage.save_project(project)
    copies = KnowledgeCopies(storage)
    original = qualify(
        ContextItem(
            content="Use approved API",
            source="org:api",
            source_type="curated",
            scope="organization",
            organization_id="ABC",
            source_version="1",
            evidence_status="verified",
        ),
        "SAP_TECHNICAL",
        "p",
    )
    first, status = copies.reconcile("p", "SAP_TECHNICAL", original)
    assert status == "adopted" and first.copied_at and first.lineage
    low = original.model_copy(update={"source_version": "2", "content": "Use  approved API"})
    adopted, status = copies.reconcile("p", "SAP_TECHNICAL", low)
    assert status == "adopted" and adopted.derived_version == 2
    material = original.model_copy(update={"source_version": "3", "content": "Use a different API"})
    retained, status = copies.reconcile("p", "SAP_TECHNICAL", material)
    assert status == "review_required" and retained.source_version == "2"
    assert storage.load_context("p", "SAP_TECHNICAL")[0].content == low.content
    confirmed, status = copies.reconcile("p", "SAP_TECHNICAL", material, approve=True, actor="local")
    assert confirmed.source_version == "3"
    denied = material.model_copy(update={"access_status": "revoked"})
    assert copies.reconcile("p", "SAP_TECHNICAL", denied)[1] == "inaccessible"
    assert storage.load_context("p", "SAP_TECHNICAL")[0].access_status == "revoked"
    records = storage.list_context_runs("p")
    assert {r["decision"] for r in records} >= {
        "inherited",
        "auto_adopted",
        "review_required",
        "approved",
        "revoked",
    }


def test_revocation_blocks_memory_and_artifact_derivatives(storage, tmp_path):
    from backend.app.runtime import Runtime
    from backend.app.models import ContextPackage

    runtime = Runtime(storage, tmp_path)
    source = qualify(
        ContextItem(content="Private integration policy", source="policy:private", source_type="curated"),
        "SAP_TECHNICAL",
        "p",
    )
    storage.save_context(
        "p", ContextPackage(project_id="p", task_id="source", sap_technical_context=[source])
    )
    runtime.memory.refresh(storage.load_state("p"))
    artifact = runtime.orchestrator.run("p", "TDD")["artifact"]
    assert artifact.evidence_provenance
    assert storage.load_memory("p").source_refs
    storage.replace_context("p", "SAP_TECHNICAL", [source.model_copy(update={"access_status": "revoked"})])
    request = runtime.orchestrator.planner.plan(storage.load_state("p"), "ABAP")
    loaded = runtime.orchestrator.context_handler.load(request)
    assert not any(i.source_type == "memory" for i in loaded.sdlc_context)
    project = storage.load_project("p")
    assert not any(
        runtime.context_planning._still_authorized(i, project)
        for i in loaded.sdlc_context
        if i.source_type == "artifact"
    )
    assert storage.load_artifact("p", "TDD") == artifact
