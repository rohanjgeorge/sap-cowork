from pathlib import Path
from .models import ArtifactType


class TemplateRepository:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[2] / "templates"

    def load(self, artifact_type):
        selected = ArtifactType(artifact_type)
        if selected == ArtifactType.ABAP:
            raise ValueError("ABAP templates belong to the replaceable module")
        content = (self.root / f"{selected.value.lower()}.md").read_text(encoding="utf-8")
        # Legacy front matter is accepted, but templates have one current file,
        # not a version registry. The second result is a structural reference.
        if content.startswith("---"):
            content = content.split("---", 2)[2]
        return content.strip(), f"{selected.value.lower()}.md"
