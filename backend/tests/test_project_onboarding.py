import pytest
from backend.app.runtime import Runtime
from backend.app.services import ApplicationService


def test_mixed_draft_and_approved_imports_persist_statuses_and_retry_without_duplication(storage, tmp_path):
    from backend.app.state_management import StateError

    service = ApplicationService(Runtime(storage, tmp_path))
    w = service.create_project(
        "Mixed documents",
        import_artifacts=["FRD", "BRD"],
        import_artifact_statuses={"BRD": "draft", "FRD": "approved"},
        request_id="mixed-create",
    )
    pid = w["project"].project_id
    assert "draft BRD" in w["onboarding"]["message"]
    with pytest.raises(StateError, match="IDENTITY_CONFLICT"):
        service.create_project(
            "Mixed documents",
            import_artifacts=["FRD", "BRD"],
            import_artifact_statuses={"BRD": "approved", "FRD": "approved"},
            request_id="mixed-create",
        )
    with pytest.raises(ValueError, match="extracted text"):
        service.import_approved_document(pid, "BRD", "empty.md", b"", request_id="empty-draft")
    assert service.open_project(pid)["onboarding"]["pending_artifacts"] == ["BRD", "FRD"]
    result = service.import_approved_document(
        pid, "BRD", "brd.md", b"Draft requirements", request_id="draft-import"
    )
    assert result["onboarding"]["pending_artifacts"] == ["FRD"]
    draft = storage.load_artifact(pid, "BRD")
    assert draft.approval_status == "draft"
    assert draft.approved_by is None
    assert result["state"].current_approved_stage == "Planning"
    service = ApplicationService(Runtime(storage, tmp_path))
    assert service.open_project(pid)["onboarding"]["artifact_statuses"] == {"BRD": "draft", "FRD": "approved"}
    assert "approved FRD" in service.open_project(pid)["onboarding"]["message"]
    final = service.import_approved_document(
        pid, "FRD", "frd.md", b"Approved functions", request_id="approved-import"
    )
    assert final["onboarding"]["complete"]
    assert storage.load_artifact(pid, "FRD").approval_status == "approved"
    for kind, text, request_id in [
        ("BRD", b"Draft requirements", "draft-import"),
        ("FRD", b"Approved functions", "approved-import"),
    ]:
        assert service.import_approved_document(pid, kind, kind.lower() + ".md", text, request_id=request_id)[
            "onboarding"
        ]["complete"]
    assert len(storage.list_artifacts(pid)) == 2
    with pytest.raises(StateError, match="IDENTITY_CONFLICT"):
        service.import_approved_document(pid, "BRD", "brd.md", b"Different draft", request_id="draft-import")


def test_import_status_api_validation_and_draft_completion(tmp_path):
    from fastapi.testclient import TestClient
    from backend.app.api import create_app

    with TestClient(create_app(data_dir=tmp_path)) as client:
        client.post("/api/session", json={"access_code": ""})
        value = {
            "project_name": "Draft API",
            "import_artifacts": ["BRD"],
            "import_artifact_statuses": {"BRD": "draft"},
        }
        assert (
            client.post(
                "/api/projects", json={**value, "import_artifact_statuses": {"FRD": "draft"}}
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/projects", json={**value, "import_artifact_statuses": {"BRD": "rejected"}}
            ).status_code
            == 422
        )
        created = client.post("/api/projects", json=value)
        assert created.status_code == 200
        pid = created.json()["project"]["project_id"]
        uploaded = client.post(
            f"/api/projects/{pid}/onboarding/upload",
            data={"artifact_type": "BRD", "request_id": "draft-api"},
            files={"file": ("brd.md", b"Draft requirements", "text/markdown")},
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["onboarding"]["complete"]
        assert uploaded.json()["state"]["artifacts"]["BRD"]["status"] == "draft"


def test_existing_artifacts_are_requested_in_sdlc_order_and_survive_reopen(storage, tmp_path):
    service = ApplicationService(Runtime(storage, tmp_path))
    w = service.create_project("Existing project", import_artifacts=["TDD", "BRD", "FRD"])
    pid = w["project"].project_id
    assert w["onboarding"]["pending_artifacts"] == ["BRD", "FRD", "TDD"]
    assert "BRD" in w["onboarding"]["message"]
    assert w["session"]["messages"][-1]["origin"] == "onboarding"
    assert ApplicationService(Runtime(storage, tmp_path)).open_project(pid)["onboarding"] == w["onboarding"]
    with pytest.raises(ValueError, match="BRD"):
        service.import_approved_document(
            pid, "FRD", "frd.md", b"Functional specification", request_id="wrong"
        )
    first = service.import_approved_document(
        pid, "BRD", "brd.md", b"Approved business requirements", request_id="brd-import"
    )
    assert first["onboarding"]["pending_artifacts"] == ["FRD", "TDD"]
    assert storage.load_artifact(pid, "BRD").approval_status == "approved"
    service.import_approved_document(
        pid, "BRD", "brd.md", b"Approved business requirements", request_id="brd-import"
    )
    assert len([a for a in storage.list_artifacts(pid) if a.artifact_id == "BRD"]) == 1
    service.import_approved_document(
        pid, "FRD", "frd.md", b"Approved functional requirements", request_id="frd-import"
    )
    final = service.import_approved_document(
        pid, "TDD", "tdd.md", b"Approved technical design", request_id="tdd-import"
    )
    assert final["onboarding"]["pending_artifacts"] == []
    assert final["onboarding"]["complete"] is True
    assert final["state"].artifacts["TDD"].status == "approved"


def test_import_does_not_advance_on_unreadable_document(storage, tmp_path):
    service = ApplicationService(Runtime(storage, tmp_path))
    w = service.create_project("Existing", import_artifacts=["BRD"])
    pid = w["project"].project_id
    with pytest.raises(ValueError, match="extracted text"):
        service.import_approved_document(pid, "BRD", "scan.png", b"not text", request_id="scan")
    assert service.open_project(pid)["onboarding"]["pending_artifacts"] == ["BRD"]


def test_scratch_projects_have_no_import_queue(storage, tmp_path):
    service = ApplicationService(Runtime(storage, tmp_path))
    assert service.create_project("Scratch")["onboarding"] is None


def test_import_retries_after_approval_failure_without_uploading_twice(storage, tmp_path, monkeypatch):
    from backend.app.state_management import StateError

    service = ApplicationService(Runtime(storage, tmp_path))
    w = service.create_project("Existing", import_artifacts=["BRD"])
    pid = w["project"].project_id
    original = service.runtime.approvals.review

    def fail(*args, **kwargs):
        raise RuntimeError("Interrupted before recording approval")

    monkeypatch.setattr(service.runtime.approvals, "review", fail)
    with pytest.raises(RuntimeError):
        service.import_approved_document(
            pid,
            "BRD",
            "brd.md",
            b"Approved requirements",
            request_id="retry",
            expected_revision=w["state"].state_revision,
        )
    assert service.open_project(pid)["onboarding"]["pending_artifacts"] == ["BRD"]
    monkeypatch.setattr(service.runtime.approvals, "review", original)
    assert service.import_approved_document(
        pid,
        "BRD",
        "brd.md",
        b"Approved requirements",
        request_id="retry",
        expected_revision=w["state"].state_revision,
    )["onboarding"]["complete"]
    assert len(storage.list_artifacts(pid)) == 1
    with pytest.raises(StateError, match="IDENTITY_CONFLICT"):
        service.import_approved_document(pid, "BRD", "brd.md", b"Different content", request_id="retry")


def test_import_api_contract(storage, tmp_path):
    from fastapi.testclient import TestClient
    from backend.app.api import create_app

    client = TestClient(create_app(data_dir=tmp_path / "api"))
    client.post("/api/session", json={"access_code": ""})
    created = client.post("/api/projects", json={"project_name": "Imported API", "import_artifacts": ["BRD"]})
    assert created.status_code == 200
    pid = created.json()["project"]["project_id"]
    rejected = client.post(
        f"/api/projects/{pid}/onboarding/upload",
        data={"artifact_type": "BRD", "request_id": "stale", "expected_revision": "999"},
        files={"file": ("brd.md", b"Approved requirements", "text/markdown")},
    )
    assert rejected.status_code == 409
    result = client.post(
        f"/api/projects/{pid}/onboarding/upload",
        data={"artifact_type": "BRD", "request_id": "import"},
        files={"file": ("brd.md", b"Approved requirements", "text/markdown")},
    )
    assert result.status_code == 200
    assert result.json()["onboarding"]["complete"]
    assert result.json()["state"]["artifacts"]["BRD"]["status"] == "approved"
