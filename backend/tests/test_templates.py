import pytest
from backend.app.templates import TemplateRepository


@pytest.mark.parametrize("kind", ["BRD", "FRD", "TDD", "UAT", "AUDIT_REPORT"])
def test_versioned_template_contract(kind):
    content, version = TemplateRepository().load(kind)
    assert version == "1.0"
    assert content.startswith("# ")
    assert "## Source References" in content
