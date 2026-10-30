"""Local provider with atomic replacement and recoverable project transactions."""

import base64
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from filelock import FileLock

from .models import Artifact, ContextItem, Project, ProjectMemory, ProjectState, uid
from .storage import StorageConflict

DOMAIN_FIELDS = {
    "BUSINESS": "business_context",
    "SAP": "sap_context",
    "ORGANIZATION": "organization_context",
    "HISTORICAL_DEVELOPMENT": "historical_context",
    "SDLC": "sdlc_context",
}


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_.-]{0,149}", value) or ".." in value:
        raise ValueError("Invalid resource identifier")
    return value


class LocalStorageProvider:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._journals: dict[str, dict] = {}

    def _project(self, project_id):
        return self.root / "project" / safe_id(project_id)

    @staticmethod
    def _atomic(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
            temp_path = Path(tmp.name)
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        try:
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)

    def _write(self, project_id, relative, value):
        project = self._project(project_id)
        path = project / relative
        journal = self._journals.get(project_id)
        if journal is not None and relative not in journal:
            journal[relative] = base64.b64encode(path.read_bytes()).decode() if path.exists() else None
            self._atomic(project / ".journal.json", json.dumps(journal).encode())
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, indent=2).encode()
        self._atomic(path, data)

    def _read(self, project_id, relative):
        return json.loads((self._project(project_id) / relative).read_text(encoding="utf-8"))

    def _rollback(self, project_id, journal):
        for relative, value in reversed(list(journal.items())):
            path = self._project(project_id) / relative
            if value is None:
                path.unlink(missing_ok=True)
            else:
                self._atomic(path, base64.b64decode(value))

    @contextmanager
    def transaction(self, project_id):
        project = self._project(project_id)
        project.mkdir(parents=True, exist_ok=True)
        with FileLock(str(project / ".lock"), timeout=30):
            if project_id in self._journals:
                raise StorageConflict("Nested project transaction")
            journal_path = project / ".journal.json"
            if journal_path.exists():
                self._rollback(project_id, json.loads(journal_path.read_text()))
                journal_path.unlink()
            journal = {}
            self._journals[project_id] = journal
            try:
                yield
            except BaseException:
                self._rollback(project_id, journal)
                journal_path.unlink(missing_ok=True)
                raise
            else:
                journal_path.unlink(missing_ok=True)
            finally:
                self._journals.pop(project_id, None)

    def create_project(self, project: Project):
        path = self._project(project.project_id)
        if (path / "project.json").exists():
            raise StorageConflict("Project already exists")
        for folder in (
            "state",
            "memory",
            "context",
            "uploads",
            "history",
            "artifacts/brd",
            "artifacts/frd",
            "artifacts/tdd",
            "artifacts/uat",
            "artifacts/abap",
            "artifacts/audit_report",
        ):
            (path / folder).mkdir(parents=True, exist_ok=True)
        self._write(project.project_id, "project.json", project.model_dump(mode="json"))

    def load_project(self, project_id):
        return Project.model_validate(self._read(project_id, "project.json"))

    def save_project(self, project):
        self._write(project.project_id, "project.json", project.model_dump(mode="json"))

    def list_projects(self):
        return sorted(
            [
                Project.model_validate_json(p.read_text(encoding="utf-8"))
                for p in (self.root / "project").glob("*/project.json")
            ],
            key=lambda p: p.updated_at,
            reverse=True,
        )

    def save_state(self, project_id, state):
        if state.project_id != project_id:
            raise ValueError("Cross-project state")
        self._write(project_id, "state/project_state.json", state.model_dump(mode="json"))

    def load_state(self, project_id):
        return ProjectState.model_validate(self._read(project_id, "state/project_state.json"))

    def save_memory(self, project_id, memory):
        if memory.project_id != project_id:
            raise ValueError("Cross-project memory")
        self._write(project_id, "memory/project_memory.json", memory.model_dump(mode="json"))
        self._write(project_id, "memory/project_memory.md", memory.content.encode())

    def load_memory(self, project_id):
        return ProjectMemory.model_validate(self._read(project_id, "memory/project_memory.json"))

    def save_artifact(self, project_id, artifact):
        if artifact.project_id != project_id:
            raise ValueError("Cross-project artifact")
        relative = (
            f"artifacts/{artifact.artifact_type.value.lower()}/"
            f"{safe_id(artifact.artifact_id)}--{safe_id(artifact.artifact_version)}.json"
        )
        path = self._project(project_id) / relative
        if path.exists():
            prior = Artifact.model_validate_json(path.read_text(encoding="utf-8"))
            if prior.content != artifact.content or prior.source_task_id != artifact.source_task_id:
                raise StorageConflict("Artifact content is immutable; create a new version")
        self._write(project_id, relative, artifact.model_dump(mode="json"))

    def _artifacts(self, project_id):
        return [
            Artifact.model_validate_json(p.read_text(encoding="utf-8"))
            for p in self._project(project_id).glob("artifacts/*/*.json")
        ]

    def load_artifact(self, project_id, artifact_id, version=None):
        safe_id(artifact_id)
        matches = [
            a
            for a in self._artifacts(project_id)
            if a.artifact_id == artifact_id and (version is None or a.artifact_version == version)
        ]
        if not matches:
            raise FileNotFoundError("Artifact not found")
        return max(matches, key=lambda a: tuple(int(v) for v in a.artifact_version.split(".")))

    def list_artifacts(self, project_id):
        return [
            a.reference()
            for a in sorted(self._artifacts(project_id), key=lambda a: a.created_date, reverse=True)
        ]

    def save_upload(self, project_id, file, metadata):
        file_id = uid()
        self._write(project_id, f"uploads/{file_id}.bin", file)
        self._write(
            project_id, f"uploads/{file_id}.json", {**metadata, "file_id": file_id, "size": len(file)}
        )
        return file_id

    def load_upload(self, project_id, file_id):
        return (self._project(project_id) / f"uploads/{safe_id(file_id)}.bin").read_bytes()

    def save_context(self, project_id, context):
        if context.project_id != project_id:
            raise ValueError("Cross-project context")
        for domain, field in DOMAIN_FIELDS.items():
            items = getattr(context, field)
            if items:
                previous = self.load_context(project_id, domain)
                merged = {item.model_dump_json(): item for item in previous + items}
                self._write(
                    project_id,
                    f"context/{domain.lower()}.json",
                    [item.model_dump() for item in merged.values()],
                )

    def load_context(self, project_id, context_type):
        domain = context_type.upper()
        if domain not in DOMAIN_FIELDS:
            raise ValueError("Unknown context domain")
        path = self._project(project_id) / f"context/{domain.lower()}.json"
        return (
            [ContextItem.model_validate(item) for item in json.loads(path.read_text(encoding="utf-8"))]
            if path.exists()
            else []
        )

    def list_project_assets(self, project_id):
        uploads = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in self._project(project_id).glob("uploads/*.json")
        ]
        return [{"kind": "upload", **u} for u in uploads] + [
            {"kind": "artifact", **a.model_dump(mode="json")} for a in self.list_artifacts(project_id)
        ]

    def load_session(self, project_id):
        try:
            return self._read(project_id, "history/session.json")
        except FileNotFoundError:
            return {"messages": [], "working_messages": [], "active_domains": [], "compactions": 0}

    def save_session(self, project_id, session):
        self._write(project_id, "history/session.json", session)

    def append_event(self, project_id, event):
        events = self.list_events(project_id)
        events.append(event)
        self._write(project_id, "history/events.json", events)

    def list_events(self, project_id):
        try:
            return self._read(project_id, "history/events.json")
        except FileNotFoundError:
            return []
