from unittest.mock import patch
from backend.app.context_handler import ContextHandler
from backend.app.models import ContextRequest, ContextPackage, ContextItem


def test_only_requested_domains_and_provenance(storage):
    storage.save_context(
        "p",
        ContextPackage(
            project_id="p",
            task_id="curation",
            sap_context=[ContextItem(content="Curated SAP input", source="sap.md", source_type="curated")],
        ),
    )
    request = ContextRequest(
        project_id="p", task_id="t", current_stage="Design", current_task="TDD", required_domains=["SAP"]
    )
    with patch.object(storage, "load_context", wraps=storage.load_context) as loader:
        package = ContextHandler(storage).load(request)
    loader.assert_called_once_with("p", "SAP")
    assert package.business_context == [] and package.sdlc_context == []
    assert package.sap_context[0].source == "sap.md"
