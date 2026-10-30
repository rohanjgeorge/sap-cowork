import pytest
from backend.app.local_storage import LocalStorageProvider
from backend.app.models import Project, ProjectState, ProjectMemory, Artifact, ContextPackage, ContextItem
from backend.app.storage import StorageProvider, StorageConflict


@pytest.fixture
def store(tmp_path):
    s = LocalStorageProvider(tmp_path)
    s.create_project(Project(project_id="p", project_name="STO"))
    s.save_state("p", ProjectState(project_id="p"))
    s.save_memory("p", ProjectMemory(project_id="p", content="Summary"))
    return s


def test_storage_contract_roundtrip_and_reopen(store):
    assert isinstance(store, StorageProvider)
    assert LocalStorageProvider(store.root).load_state("p").current_stage == "Planning"
    assert store.load_memory("p").content == "Summary"
    artifact = Artifact(
        artifact_id="BRD",
        project_id="p",
        artifact_type="BRD",
        content="# BRD",
        artifact_version="1",
        template_version="1",
    )
    store.save_artifact("p", artifact)
    assert store.load_artifact("p", "BRD").content == "# BRD"
    assert len(store.list_artifacts("p")) == 1
    file_id = store.save_upload("p", b"CR", {"name": "input.txt"})
    assert store.load_upload("p", file_id) == b"CR"
    assert len(store.list_project_assets("p")) == 2
    package = ContextPackage(
        project_id="p",
        task_id="t",
        sap_context=[ContextItem(content="SAP fact", source="reference", source_type="curated")],
    )
    store.save_context("p", package)
    assert store.load_context("p", "SAP")[0].source == "reference"
    assert store.load_context("p", "BUSINESS") == []


def test_transaction_rolls_back_all_writes(store):
    before = store.load_state("p")
    with pytest.raises(OSError):
        with store.transaction("p"):
            state = store.load_state("p")
            state.current_task = "wrong"
            store.save_state("p", state)
            store.save_upload("p", b"bad", {"name": "bad"})
            raise OSError("disk full")
    assert store.load_state("p") == before
    assert store.list_project_assets("p") == []


def test_immutable_versions_and_path_boundaries(store):
    a = Artifact(
        artifact_id="BRD",
        project_id="p",
        artifact_type="BRD",
        content="original",
        artifact_version="1",
        template_version="1",
    )
    store.save_artifact("p", a)
    a.content = "overwrite"
    with pytest.raises(StorageConflict):
        store.save_artifact("p", a)
    with pytest.raises(ValueError):
        store.load_project("../outside")
    with pytest.raises(ValueError):
        store.save_state("p", ProjectState(project_id="other"))
