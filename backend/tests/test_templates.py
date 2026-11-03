import pytest
from backend.app.templates import TemplateRepository


@pytest.mark.parametrize("kind", ["BRD", "FRD", "USER_STORIES", "TDD", "SIT", "UAT", "AUDIT_REPORT"])
def test_current_template_reference_contract(kind):
    content, version = TemplateRepository().load(kind)
    assert version == f"{kind.lower()}.md"
    assert content.startswith("# ")
    assert "## Version History" in content
