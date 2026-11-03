from io import BytesIO

from docx import Document
import pytest

from backend.app.artifact_lifecycle import ArtifactLifecycle
from backend.app.document_conversion import from_docx
from backend.app.local_storage import LocalStorageProvider
from backend.app.models import Artifact, Project
from backend.app.state_management import StateManagementService


def setup(tmp_path):
    storage = LocalStorageProvider(tmp_path)
    states = StateManagementService(storage)
    states.create_project(Project(project_id="p", project_name="CR"))
    return storage, states, ArtifactLifecycle(storage, states)


def sample(kind="BRD"):
    return Artifact(
        artifact_id=kind,
        artifact_type=kind,
        project_id="p",
        content="# Document\n\n## Scope\nSource facts",
        artifact_version="1",
        template_version=f"{kind.lower()}.md",
    )


def test_draft_edits_approved_fork_docx_archive_and_restore(tmp_path):
    storage, states, artifacts = setup(tmp_path)
    first, state = artifacts.persist(sample(), storage.load_state("p"))
    assert first.approval_status == "draft"
    edited, state = artifacts.edit("p", "BRD", first.content.replace("Source facts", "Updated facts"))
    assert edited.artifact_version == "1"
    states.apply("p", "approve_artifact", {"artifact_id": "BRD", "version": "1"})
    original = storage.load_artifact("p", "BRD", "1").content
    updated, _ = artifacts.edit("p", "BRD", original + "\nNew requirement")
    assert updated.artifact_version == "2" and updated.approval_status == "draft"
    assert storage.load_artifact("p", "BRD", "1").content == original
    assert (tmp_path / "project/p/artifacts/brd/archive/BRD_v1.docx").exists()
    data = storage.load_artifact_document("p", "BRD")
    assert any(p.text == "Version History" for p in Document(BytesIO(data)).paragraphs)
    assert "Updated facts" in from_docx(data)
    artifacts.delete("p", "BRD", "2")
    assert storage.load_artifact("p", "BRD").artifact_version == "1"
    assert storage.next_artifact_version("p", "BRD") == "3"


def test_explicit_version_requires_authors_and_remarks(tmp_path):
    storage, _, artifacts = setup(tmp_path)
    artifacts.persist(sample(), storage.load_state("p"))
    with pytest.raises(ValueError, match="Authors and remarks"):
        artifacts.edit("p", "BRD", "updated", new_version=True)
    artifact, _ = artifacts.edit(
        "p", "BRD", "updated", new_version=True, authors="Rohan", remarks="Scope change"
    )
    assert artifact.artifact_version == "2"
    assert artifact.version_history[-1]["authors"] == "Rohan"


def test_upstream_change_forks_approved_downstream_without_applying_recommendations(tmp_path):
    storage, states, artifacts = setup(tmp_path)
    brd, _ = artifacts.persist(sample(), storage.load_state("p"))
    states.apply("p", "approve_artifact", {"artifact_id": "BRD", "version": "1"})
    frd = sample("FRD")
    frd.upstream = [brd.reference()]
    artifacts.persist(frd, storage.load_state("p"))
    states.apply("p", "approve_artifact", {"artifact_id": "FRD", "version": "1"})
    before = storage.load_artifact("p", "FRD", "1")
    artifacts.edit("p", "BRD", brd.content + "\nScope has changed")
    after = storage.load_artifact("p", "FRD")
    assert after.artifact_version == "2" and after.approval_status == "draft"
    assert after.recommendations
    assert "Scope has changed" not in after.content
    assert storage.load_artifact("p", "FRD", "1") == before


def test_valid_document_survives_registration_failure_and_can_reconcile(tmp_path, monkeypatch):
    storage, states, artifacts = setup(tmp_path)
    apply = states.apply
    monkeypatch.setattr(
        states, "apply", lambda *a, **k: (_ for _ in ()).throw(OSError("registration unavailable"))
    )
    with pytest.raises(OSError):
        artifacts.persist(sample(), storage.load_state("p"))
    assert storage.load_artifact("p", "BRD").content
    monkeypatch.setattr(states, "apply", apply)
    assert states.apply("p", "reconcile_artifacts").artifacts["BRD"].latest_version == 1


def test_offline_comparison_and_alignment_preserve_source_without_invention(tmp_path):
    storage, _, artifacts = setup(tmp_path)
    artifacts.persist(sample(), storage.load_state("p"))
    comparison = artifacts.compare("p", "BRD", "Completely different source")
    assert comparison["significant"] and "uploaded" in comparison["diff"]
    aligned = artifacts.align_upload("BRD", "Company-specific source")
    assert "Company-specific source" in aligned and "TBD" in aligned
