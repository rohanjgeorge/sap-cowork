from fastapi.testclient import TestClient

from backend.app.api import create_app
from backend.app.context_sources import qualify
from backend.app.models import ContextItem, ContextPackage
from backend.app.settings import MemorySecretStore


def test_context_reports_original_sources_and_rechecks_revoked_copy_permissions(tmp_path):
    app = create_app(tmp_path, MemorySecretStore(), access_code="")
    with TestClient(app) as client:
        client.post("/api/session", json={"access_code": ""})
        project = client.post(
            "/api/projects",
            json={"project_name": "Evidence", "requirement": "STO automation", "organization_id": "ABC"},
        ).json()
        p = project["project"]["project_id"]
        runtime = app.state.runtime
        evidence = qualify(
            ContextItem(
                content="Protected organization technical reference",
                source="organization:technical",
                source_type="curated",
                scope="organization",
                organization_id="ABC",
                source_version="1",
            ),
            "SAP_TECHNICAL",
            p,
        )
        runtime.context_planning.copies.reconcile(p, "SAP_TECHNICAL", evidence)
        generated = client.post(
            f"/api/projects/{p}/chat", json={"action": "generate", "artifact_type": "TDD"}
        ).json()
        ref = generated["artifact"]["context_plan_ref"]
        report = client.get(f"/api/projects/{p}/context/plans/{ref}")
        assert report.status_code == 200
        assert "Protected organization technical reference" in report.text
        catalog = client.get(f"/api/projects/{p}/context/sources").json()
        assert len(catalog) == 9 and all(not source["configured_adapters"] for source in catalog)
        assert client.get(f"/api/projects/{p}/context/plans").json()[0]["profile_version"] == "1.0"
        runtime.context_planning.copies.reconcile(
            p, "SAP_TECHNICAL", evidence.model_copy(update={"access_status": "revoked"})
        )
        assert (
            "Protected organization technical reference"
            not in client.get(f"/api/projects/{p}/context/plans/{ref}").text
        )


def test_material_knowledge_review_requires_comparison_and_retains_artifacts(tmp_path):
    app = create_app(tmp_path, MemorySecretStore(), access_code="")
    with TestClient(app) as client:
        client.post("/api/session", json={"access_code": ""})
        p = client.post(
            "/api/projects", json={"project_name": "Review", "requirement": "STO", "organization_id": "ABC"}
        ).json()["project"]["project_id"]
        runtime = app.state.runtime
        copies = runtime.context_planning.copies
        old = qualify(
            ContextItem(
                content="Original coding policy",
                source="org:policy",
                source_type="curated",
                scope="organization",
                organization_id="ABC",
                source_version="1",
                evidence_status="verified",
            ),
            "STANDARDS_GOVERNANCE",
            p,
        )
        copies.reconcile(p, "STANDARDS_GOVERNANCE", old)
        client.post(f"/api/projects/{p}/chat", json={"action": "generate", "artifact_type": "BRD"})
        client.post(f"/api/projects/{p}/artifacts/BRD/review", json={"action": "approve", "version": "1"})
        before = runtime.storage.load_artifact(p, "BRD")
        incoming = old.model_copy(update={"content": "New mandatory security policy", "source_version": "2"})
        copies.reconcile(p, "STANDARDS_GOVERNANCE", incoming)
        copies.reconcile(p, "STANDARDS_GOVERNANCE", incoming)
        updates = client.get(f"/api/projects/{p}/context/updates").json()
        assert len(updates) == 1
        ref = updates[0]["record_id"]
        root = f"/api/projects/{p}/context/updates/{ref}"
        assert client.post(root + "/review", json={"approved": True}).status_code == 409
        comparison = client.get(root).json()
        assert "-Original coding policy" in comparison["diff"]
        assert "+New mandatory security policy" in comparison["diff"]
        accepted = client.post(
            root + "/review",
            json={"approved": True, "expected_fingerprint": comparison["current_fingerprint"]},
        )
        assert accepted.status_code == 200, accepted.text
        assert "incoming" not in accepted.json()
        assert runtime.storage.load_context(p, "STANDARDS_GOVERNANCE")[0].source_version == "2"
        assert runtime.storage.load_artifact(p, "BRD") == before


def test_conflicting_structured_sources_are_retained_and_qualified(storage, tmp_path):
    from backend.app.runtime import Runtime

    runtime = Runtime(storage, tmp_path)
    storage.save_context(
        "p",
        ContextPackage(
            project_id="p",
            task_id="source",
            standards_governance_context=[
                ContextItem(
                    content="Policy A",
                    source="policy:a",
                    source_type="curated",
                    source_category="SRC-06",
                    structured_facts={"naming": "Z_A"},
                ),
                ContextItem(
                    content="Policy B",
                    source="policy:b",
                    source_type="curated",
                    source_category="SRC-06",
                    structured_facts={"naming": "Z_B"},
                ),
            ],
        ),
    )
    result = runtime.orchestrator.run("p", "TDD")
    assert result["artifact"]
    assert any(g.gap_type == "conflict" for g in result["artifact"].context_gaps)
    record = storage.load_context_run("p", result["artifact"].context_plan_ref)
    assert len([i for i in record["evidence"] if i["source"].startswith("policy:") and i["conflict"]]) == 2
