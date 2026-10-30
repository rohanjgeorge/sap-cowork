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
        metadata, body = content.split("---", 2)[1:]
        version = next(
            line.split(":", 1)[1].strip()
            for line in metadata.splitlines()
            if line.startswith("template_version:")
        )
        return body.strip(), version
