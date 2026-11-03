"""Document versioning, provenance, comparison and impact recommendations."""

from difflib import SequenceMatcher, unified_diff
import re

from .models import now
from .router import UPSTREAM
from .templates import TemplateRepository


def version_for(storage, project_id, kind, inputs=None):
    inputs = inputs or {}
    if inputs.get("new_version") and (
        not inputs.get("authors", "").strip() or not inputs.get("remarks", "").strip()
    ):
        raise ValueError("Authors and remarks are required for an explicit new version")
    try:
        current = storage.load_artifact(project_id, kind)
    except FileNotFoundError:
        current = None
    if current and current.approval_status != "approved" and not inputs.get("new_version"):
        return current.artifact_version
    return storage.next_artifact_version(project_id, kind)


class ArtifactLifecycle:
    def __init__(self, storage, state_service):
        self.storage, self.state_service = storage, state_service

    def _history(self, artifact, prior, authors, remarks):
        def sections(content):
            parts = re.split(r"(?m)^(#{1,3} .+)\s*$", content)
            return {
                parts[i]: parts[i + 1].strip()
                for i in range(1, len(parts) - 1, 2)
                if parts[i] != "## Version History"
            }

        before, after = sections(prior.content if prior else ""), sections(artifact.content)
        changed = [name for name in dict.fromkeys([*before, *after]) if before.get(name) != after.get(name)]
        modified = (
            ("; ".join(name.lstrip("# ") for name in changed) or "Document content / metadata")
            if prior
            else "All sections — initial document"
        )
        history = list(prior.version_history) if prior else []
        if prior and not history:
            history.append(
                {
                    "version": prior.artifact_version,
                    "created_at": prior.created_date.isoformat(),
                    "authors": prior.edited_by or "Not recorded",
                    "sections_modified": "Historical content; change details not recorded",
                    "remarks": "Existing version; original change reason not recorded",
                }
            )
        if not history or history[-1].get("version") != artifact.artifact_version:
            history.append(
                {
                    "version": artifact.artifact_version,
                    "created_at": now().isoformat(),
                    "authors": authors,
                    "sections_modified": modified,
                    "remarks": remarks,
                }
            )
        else:
            history[-1] = {
                **history[-1],
                "authors": authors,
                "remarks": remarks,
                "edited_at": now().isoformat(),
                "sections_modified": modified,
            }
        artifact.version_history = history
        if artifact.artifact_type == "ABAP":
            return
        rows = ["| Version | Created Date | Authors | Sections Modified | Remarks |", "|---|---|---|---|---|"]
        for record in history:
            values = [
                record.get(k, "")
                for k in ("version", "created_at", "authors", "sections_modified", "remarks")
            ]
            values[1] = str(values[1])[:10]
            rows.append("| " + " | ".join(str(v).replace("|", "/").replace("\n", " ") for v in values) + " |")
        section = "## Version History\n\n" + "\n".join(rows) + "\n\n"
        if "## Version History" in artifact.content:
            artifact.content = re.sub(
                r"^## Version History\s*\n.*?(?=^## |\Z)",
                lambda _: section,
                artifact.content,
                count=1,
                flags=re.M | re.S,
            )
        else:
            artifact.content += "\n\n" + section

    def save_output(self, artifact, state, inputs=None, *, on_saved=None):
        inputs = inputs or {}
        current = self.storage.load_state(state.project_id)
        self.state_service.require_active(current)
        if current.state_revision != state.state_revision:
            from .state_management import StateError

            raise StateError(
                "REVISION_CONFLICT", "Artifact generation used stale state", current.state_revision
            )
        try:
            prior = self.storage.load_artifact(state.project_id, artifact.artifact_id)
        except FileNotFoundError:
            prior = None
        if (
            artifact.artifact_type == "ABAP"
            and prior
            and prior.content != artifact.content
            and artifact.artifact_version == prior.artifact_version
        ):
            artifact.artifact_version = self.storage.next_artifact_version(
                state.project_id, artifact.artifact_id
            )
        elif artifact.artifact_type != "ABAP":
            artifact.artifact_version = version_for(
                self.storage, state.project_id, artifact.artifact_id, inputs
            )
        artifact.approval_status = "draft"
        artifact.approved_by = artifact.approved_at = artifact.approval_declared_by = None
        artifact.edited_by = inputs.get("authors") or "local"
        artifact.last_edited_date = now()
        if prior and prior.artifact_version == artifact.artifact_version:
            artifact.created_date = prior.created_date
        self._history(
            artifact,
            prior,
            artifact.edited_by,
            inputs.get("remarks") or inputs.get("instructions") or "Generated / updated through CoWork",
        )
        # Persist the complete valid document before registry commit. A failed
        # registration leaves a recoverable artifact, not a partial model output.
        with self.storage.transaction(state.project_id):
            fresh = self.storage.load_state(state.project_id)
            if fresh.state_revision != state.state_revision:
                from .state_management import StateError

                raise StateError(
                    "REVISION_CONFLICT", "State changed before artifact save", fresh.state_revision
                )
            self.storage.save_artifact(state.project_id, artifact)
            if on_saved:
                on_saved(artifact, prior)
        return artifact, prior

    def register_output(self, artifact, state, *, request_id=None):
        return self.state_service.apply(
            state.project_id,
            "register_artifact",
            {"artifact_id": artifact.artifact_id, "version": artifact.artifact_version},
            expected_revision=state.state_revision,
            request_id=request_id,
        )

    def persist(self, artifact, state, inputs=None, *, impact=True):
        artifact, prior = self.save_output(artifact, state, inputs)
        updated = self.register_output(artifact, state, request_id=(inputs or {}).get("request_id"))
        if impact and prior and prior.content != artifact.content:
            updated = self._impact(artifact, updated)
        return artifact, updated

    def _impact(self, upstream, state):
        for ref in list(state.artifact_registry):
            downstream = self.storage.load_artifact(state.project_id, ref.artifact_id)
            if downstream.artifact_id == upstream.artifact_id:
                continue
            linked = any(r.artifact_id == upstream.artifact_id for r in downstream.upstream)
            if not linked:
                linked = UPSTREAM.get(downstream.artifact_type) == upstream.artifact_type
            if not linked:
                continue
            from hashlib import sha256

            headings = re.findall(r"^## (.+)$", downstream.content, re.M)
            note = (
                f"Review sections using {upstream.artifact_id}: source changed to v{upstream.artifact_version} "
                f"({sha256(upstream.content.encode()).hexdigest()[:12]}). "
                f"Sections for revalidation: {'; '.join(headings) or 'entire document'}. "
                "Confirm recommended revisions before applying content changes."
            )
            if note in downstream.recommendations:
                continue
            if downstream.approval_status == "approved":
                downstream = downstream.model_copy(deep=True)
                downstream.artifact_version = self.storage.next_artifact_version(
                    state.project_id, downstream.artifact_id
                )
                downstream.source_task_id = None
            downstream.recommendations.append(note)
            _, state = self.persist(downstream, state, {"remarks": note}, impact=False)
            state = self.state_service.apply(
                state.project_id,
                "add_flag",
                {
                    "description": note,
                    "related_artifact": downstream.artifact_id,
                },
                expected_revision=state.state_revision,
            )
        return state

    def edit(
        self,
        project_id,
        artifact_id,
        content,
        *,
        new_version=False,
        authors="",
        remarks="",
        expected_revision=None,
        request_id=None,
    ):
        state = self.storage.load_state(project_id)
        if expected_revision is not None and expected_revision != state.state_revision:
            from .state_management import StateError

            raise StateError("REVISION_CONFLICT", "Reload before editing", state.state_revision)
        artifact = self.storage.load_artifact(project_id, artifact_id).model_copy(deep=True)
        artifact.content = content
        artifact.source_task_id = None
        return self.persist(
            artifact,
            state,
            {"new_version": new_version, "authors": authors, "remarks": remarks, "request_id": request_id},
        )

    def compare(self, project_id, artifact_id, content):
        prior = self.storage.load_artifact(project_id, artifact_id)
        ratio = SequenceMatcher(None, prior.content, content).ratio()
        return {
            "significant": ratio < 0.8,
            "similarity": ratio,
            "diff": "\n".join(
                unified_diff(
                    prior.content.splitlines(),
                    content.splitlines(),
                    fromfile=f"stored v{prior.artifact_version}",
                    tofile="uploaded",
                )
            ),
        }

    def align_upload(self, kind, content):
        if kind == "ABAP":
            return content
        template, _ = TemplateRepository().load(kind)
        required = re.findall(r"^#{1,2} .+$", template, re.M)
        actual = re.findall(r"^#{1,2} .+$", content, re.M)
        if actual == required:
            return content
        # Preserve every supplied fact without inventing a section mapping.
        return (
            "\n\n".join(h + "\n\nTBD — review alignment against the uploaded source." for h in required)
            + "\n\n### Original uploaded source for review\n\n"
            + content
        )

    def delete(self, project_id, artifact_id, version, *, expected_revision=None, request_id=None):
        self.state_service.require_active(self.storage.load_state(project_id))
        with self.storage.transaction(project_id):
            fresh = self.storage.load_state(project_id)
            if expected_revision is not None and fresh.state_revision != expected_revision:
                from .state_management import StateError

                raise StateError("REVISION_CONFLICT", "Reload before deleting", fresh.state_revision)
            self.storage.delete_artifact(project_id, artifact_id, version)
        return self.state_service.apply(
            project_id, "reconcile_artifacts", expected_revision=expected_revision, request_id=request_id
        )
