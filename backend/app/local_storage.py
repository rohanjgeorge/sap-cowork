"""Local provider with atomic replacement and recoverable project transactions."""

import base64
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from filelock import FileLock, Timeout

from .models import Artifact, ContextItem, Project, ProjectMemory, ProjectState, uid
from .storage import StorageConflict

from .context_domains import DOMAIN_FIELDS


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

    def execution_lock(self, project_id):
        project = self._project(project_id)
        project.mkdir(parents=True, exist_ok=True)
        return FileLock(str(project / ".execution.lock"), timeout=180)

    def mutation_lock(self, project_id):
        project = self._project(project_id)
        project.mkdir(parents=True, exist_ok=True)
        return FileLock(str(project / ".mutation.lock"), timeout=180)

    def task_running(self, project_id):
        lock = self.execution_lock(project_id)
        try:
            with lock.acquire(timeout=0):
                return False
        except Timeout:
            return True

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
        # Both files participate in the same project journal. A committed backup
        # therefore represents the latest verified state, including its revision.
        self._write(project_id, "state/project_state.backup.json", state.model_dump(mode="json"))

    def load_state(self, project_id):
        try:
            return ProjectState.model_validate(self._read(project_id, "state/project_state.json"))
        except ValueError:
            backup = ProjectState.model_validate(self._read(project_id, "state/project_state.backup.json"))
            self._atomic(
                self._project(project_id) / "state/project_state.json", backup.model_dump_json().encode()
            )
            return backup

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
            if prior.approval_status == "approved" and (
                prior.content != artifact.content
                or prior.source_task_id != artifact.source_task_id
                or artifact.approval_status != "approved"
                or artifact.deleted
            ):
                raise StorageConflict("Approved artifact is immutable; create a new draft version")
        from .document_conversion import to_docx

        directory = f"artifacts/{artifact.artifact_type.value.lower()}"
        previous = [a for a in self._artifacts(project_id) if a.artifact_id == artifact.artifact_id]
        active = max(previous, key=lambda a: int(a.artifact_version), default=None)
        if active and int(active.artifact_version) < int(artifact.artifact_version):
            extension = "abap" if active.artifact_type == "ABAP" else "docx"
            content = active.content.encode() if extension == "abap" else to_docx(active)
            self._write(
                project_id,
                f"{directory}/archive/{active.artifact_id}_v{active.artifact_version}.{extension}",
                content,
            )
        self._write(project_id, relative, artifact.model_dump(mode="json"))
        versions = [a for a in self._artifacts(project_id) if a.artifact_id == artifact.artifact_id]
        latest = max(versions, key=lambda a: int(a.artifact_version), default=None)
        extension = "abap" if artifact.artifact_type == "ABAP" else "docx"
        if latest:
            content = latest.content.encode() if extension == "abap" else to_docx(latest)
            self._write(project_id, f"{directory}/current/{artifact.artifact_id}.{extension}", content)
        else:
            current = f"{directory}/current/{artifact.artifact_id}.{extension}"
            self._write(project_id, current, b"")
            (self._project(project_id) / current).unlink(missing_ok=True)
        if latest is None or latest.artifact_version != artifact.artifact_version:
            content = artifact.content.encode() if extension == "abap" else to_docx(artifact)
            self._write(
                project_id,
                f"{directory}/archive/{artifact.artifact_id}_v{artifact.artifact_version}.{extension}",
                content,
            )

    def _artifacts(self, project_id, include_deleted=False):
        return [
            a
            for p in self._project(project_id).glob("artifacts/*/*.json")
            for a in [Artifact.model_validate_json(p.read_text(encoding="utf-8"))]
            if include_deleted or not a.deleted
        ]

    def load_artifact(self, project_id, artifact_id, version=None):
        safe_id(artifact_id)
        version = str(version) if version is not None else None
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

    def next_artifact_version(self, project_id, artifact_id):
        return str(
            max(
                (
                    int(a.artifact_version)
                    for a in self._artifacts(project_id, True)
                    if a.artifact_id == artifact_id
                ),
                default=0,
            )
            + 1
        )

    def load_artifact_document(self, project_id, artifact_id, version=None):
        from .document_conversion import to_docx

        artifact = self.load_artifact(project_id, artifact_id, version)
        return artifact.content.encode() if artifact.artifact_type == "ABAP" else to_docx(artifact)

    def delete_artifact(self, project_id, artifact_id, version):
        artifact = self.load_artifact(project_id, artifact_id, version)
        latest = self.load_artifact(project_id, artifact_id)
        if latest.artifact_version != version or artifact.approval_status != "draft":
            raise StorageConflict("Only the active Draft can be deleted")
        artifact.deleted = True
        self.save_artifact(project_id, artifact)

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
                    [item.model_dump(mode="json") for item in merged.values()],
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

    def replace_context(self, project_id, context_type, items):
        domain = context_type.upper()
        if domain not in DOMAIN_FIELDS:
            raise ValueError("Unknown context domain")
        self._write(
            project_id, f"context/{domain.lower()}.json", [item.model_dump(mode="json") for item in items]
        )

    def save_context_run(self, project_id, run_id, value):
        self._write(project_id, f"context/runs/{safe_id(run_id)}.json", value)

    def load_context_run(self, project_id, run_id):
        return self._read(project_id, f"context/runs/{safe_id(run_id)}.json")

    def list_context_runs(self, project_id):
        return [
            json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(self._project(project_id).glob("context/runs/*.json"))
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
