import pytest
from backend.app.local_storage import LocalStorageProvider
from backend.app.models import Project, ProjectMemory, ProjectState


@pytest.fixture
def storage(tmp_path):
    store = LocalStorageProvider(tmp_path)
    store.create_project(Project(project_id="p", project_name="STO Automation"))
    store.save_state("p", ProjectState(project_id="p", requirement="Automate STO deliveries"))
    store.save_memory("p", ProjectMemory(project_id="p"))
    return store
