"""Source identity, claim-specific evidence policy and controlled project copies.

No network source is enabled by this module. Adapters are explicitly registered
by the composition root; catalog links describe proposed sources only.
"""

from concurrent.futures import ThreadPoolExecutor, wait
from hashlib import sha256
import re
import json
from time import monotonic
from typing import Protocol

from .models import ContextItem, Project, SourceCategory as S, now, uid
from .context_domains import DOMAIN_FIELDS


def origin_refs(metadata):
    found = {}
    for value in metadata:
        raw = value.model_dump(mode="json") if isinstance(value, ContextItem) else value
        if raw.get("derivation_refs"):
            for ref in raw["derivation_refs"]:
                found[ref["source_id"]] = ref
        elif (
            raw.get("source_type") in ("curated", "upload", "connector", "repository", "research")
            or raw.get("scope") == "organization"
        ):
            item = ContextItem.model_validate({**raw, "content": raw.get("content", "")})
            found[identity(item)] = {
                "source_id": identity(item),
                "source": item.source,
                "domain": str(item.domain) if item.domain else None,
                "source_version": item.source_version,
                "content_digest": item.content_digest,
                "adapter_id": item.adapter_id,
            }
    return list(found.values())[:64]


def references_allowed(refs, storage, project, registry=None, *, strict_versions=False):
    current = {
        identity(item): item
        for domain in DOMAIN_FIELDS
        for item in storage.load_context(project.project_id, domain)
    }
    if not refs:
        return not any(not permitted(item, project) for item in current.values())
    for ref in refs:
        item = current.get(ref["source_id"])
        if item is None:
            if ref.get("adapter_id") and registry and registry.authorized(ref["adapter_id"], project):
                continue
            return False
        if (
            not permitted(item, project)
            or item.adapter_id
            and (registry is None or not registry.authorized(item.adapter_id, project))
        ):
            return False
        if strict_versions and (
            item.source_version != ref.get("source_version")
            or ref.get("content_digest")
            and sha256(item.content.encode()).hexdigest() != ref["content_digest"]
        ):
            return False
    return True


SOURCE_CATALOG = {
    S.CONVERSATION: ("Project conversation", None),
    S.UPLOAD: ("Original uploads", None),
    S.ARTIFACT: ("Project artifact registry", None),
    S.STATE_MEMORY: ("Project state and memory", None),
    S.SAP_STANDARD: ("Official SAP references", "https://help.sap.com"),
    S.ORGANIZATION: ("Organization knowledge", None),
    S.HISTORICAL: ("Historical development", None),
    S.CONNECTED_SYSTEM: ("Authorized customer systems", None),
    S.SUPPORT_COMMUNITY: ("Support and community", "https://community.sap.com"),
}
SOURCE_LINKS = {
    S.SAP_STANDARD: [
        "https://help.sap.com",
        "https://help.sap.com/docs/abap-cloud/abap-keywords-standard-abap/abenabap.html",
        "https://developers.sap.com",
        "https://api.sap.com",
    ],
    S.SUPPORT_COMMUNITY: ["https://me.sap.com", "https://community.sap.com"],
}


def identity(item):
    return item.source_id or sha256((item.original_uri or item.origin or item.source).encode()).hexdigest()


def evidence_id(item):
    return sha256(
        f"{identity(item)}:{item.source_version}:{item.derived_version}:{item.content_digest or sha256(item.content.encode()).hexdigest()}".encode()
    ).hexdigest()


def permitted(item: ContextItem, project: Project, user="local"):
    return (
        item.access_status == "allowed"
        and (not item.tenant_id or item.tenant_id == project.tenant_id)
        and (not item.organization_id or item.organization_id == project.organization_id)
        and (not item.project_id or item.project_id == project.project_id)
        and (not item.program_id or item.program_id == project.program_id)
        and (not item.allowed_users or user in item.allowed_users)
        and (not item.allowed_projects or project.project_id in item.allowed_projects)
        and not (item.scope == "global" and item.confidential)
    )


def qualify(item, domain, project_id):
    result = item.model_copy(deep=True)
    result.domain = result.domain or domain
    result.source_id = identity(result)
    result.content_digest = result.content_digest or sha256(result.content.encode()).hexdigest()
    result.original_uri = result.original_uri or result.origin or result.source
    result.acquisition_method = result.acquisition_method or result.source_type
    if result.source_type in ("user", "conversation", "upload", "artifact", "state", "memory"):
        result.observed_at = result.observed_at or now()
    category = {
        "user": S.CONVERSATION,
        "conversation": S.CONVERSATION,
        "upload": S.UPLOAD,
        "artifact": S.ARTIFACT,
        "state": S.STATE_MEMORY,
        "memory": S.STATE_MEMORY,
        "connector": S.CONNECTED_SYSTEM,
        "repository": S.CONNECTED_SYSTEM,
        "research": S.SAP_STANDARD,
    }.get(result.source_type)
    if category is None:
        category = (
            S.HISTORICAL
            if domain == "HISTORICAL_DEVELOPMENT"
            else S.ORGANIZATION
            if result.scope == "organization"
            else S.SAP_STANDARD
        )
    result.source_category = result.source_category or category
    if result.scope == "project":
        result.project_id = result.project_id or project_id
    if result.qualification in ("verified", "supported", "inferred", "disputed"):
        result.evidence_status = result.qualification
    if result.conflict:
        result.evidence_status = "disputed"
    if (
        result.source_type in ("curated", "connector", "repository", "research")
        and not result.effective_from
        and not result.effective_to
        and "effective validity interval not supplied" not in result.qualification
    ):
        result.qualification = (
            result.qualification
            + "; effective validity interval not supplied; observation does not establish historical or future validity"
        )
    # Source category does not establish authority or truth on its own.
    if result.source_type in ("artifact", "state", "user", "conversation"):
        result.authority = "project"
        if result.evidence_status == "unknown":
            result.evidence_status = "supported"
    return result


class ContextSourceAdapter(Protocol):
    adapter_id: str
    category: S

    def authorized(self, project: Project, user: str) -> bool: ...
    def discover(self, project: Project, requirements: list) -> list[dict]: ...
    def retrieve(self, project: Project, action: dict, *, timeout_seconds: float) -> list[ContextItem]: ...


class SourceRegistry:
    def __init__(self):
        self.adapters = {}
        self.target_bindings = {}

    def register(self, adapter, *, target_binding=None):
        if len(self.adapters) >= 16:
            raise ValueError("At most 16 explicitly configured source adapters are supported")
        if adapter.adapter_id in self.adapters:
            raise ValueError("Source adapter already registered")
        self.adapters[adapter.adapter_id] = adapter
        if target_binding:
            if not (target_binding.get("project_id") or target_binding.get("organization_id")):
                raise ValueError("Trusted SAP binding requires project or organization scope")
            self.target_bindings[adapter.adapter_id] = target_binding

    def sap_target(self, project):
        explicit = project.sap_applicability
        values = {}
        for adapter_id, binding in self.target_bindings.items():
            if not self.authorized(adapter_id, project):
                continue
            if binding.get("project_id") and binding["project_id"] != project.project_id:
                continue
            if binding.get("organization_id") and binding["organization_id"] != project.organization_id:
                continue
            incoming = binding.get("applicability", {})
            if any(k in explicit and explicit[k] != v for k, v in incoming.items()):
                continue
            for key, value in incoming.items():
                values.setdefault(key, set()).add(value)
        return {**{k: next(iter(v)) for k, v in values.items() if len(v) == 1}, **explicit}

    def authorized(self, adapter_id, project, user="local"):
        try:
            return adapter_id in self.adapters and bool(self.adapters[adapter_id].authorized(project, user))
        except Exception:
            return False

    def catalog(self, project, user="local"):
        return [
            {
                "category": category.value,
                "name": name,
                "reference_url": url,
                "reference_urls": SOURCE_LINKS.get(category, []),
                "configured_adapters": sorted(
                    a.adapter_id
                    for a in self.adapters.values()
                    if a.category == category and self.authorized(a.adapter_id, project, user)
                ),
                "local_project_sources": category in (S.CONVERSATION, S.UPLOAD, S.ARTIFACT, S.STATE_MEMORY),
            }
            for category, (name, url) in SOURCE_CATALOG.items()
        ]

    def discover(self, project, requirements, user="local", timeout_seconds=10):
        actions, failures = [], []
        categories = {c for r in requirements for c in r.source_categories}
        pool = ThreadPoolExecutor(max_workers=4)
        pending = {}
        for adapter_id, adapter in sorted(self.adapters.items()):
            if adapter.category not in categories:
                continue
            try:
                if not adapter.authorized(project, user):
                    failures.append({"source": adapter_id, "reason": "inaccessible"})
                    continue
                pending[pool.submit(adapter.discover, project, requirements)] = adapter
            except Exception:
                failures.append({"source": adapter_id, "reason": "unavailable"})
        completed, unfinished = (
            wait(pending, timeout=max(0.01, timeout_seconds)) if pending else (set(), set())
        )
        for future in sorted(completed, key=lambda f: pending[f].adapter_id):
            adapter = pending[future]
            try:
                for candidate in future.result()[:20]:
                    actions.append(
                        {
                            **candidate,
                            "adapter_id": adapter.adapter_id,
                            "category": adapter.category.value,
                            "research": bool(getattr(adapter, "research", False)),
                        }
                    )
            except Exception:
                failures.append({"source": adapter.adapter_id, "reason": "unavailable"})
        for future in unfinished:
            future.cancel()
            failures.append({"source": pending[future].adapter_id, "reason": "budget"})
        pool.shutdown(wait=False, cancel_futures=True)
        return actions, failures

    def retrieve(self, project, actions, *, timeout_seconds, max_workers=4, user="local"):
        """Adapters must honor their timeout. Late results are never merged."""
        started = monotonic()
        executed = set()
        parallel = all(
            a.get("independent") and getattr(self.adapters[a["adapter_id"]], "parallel_safe", False)
            for a in actions
        )
        pool = ThreadPoolExecutor(max_workers=max_workers if parallel else 1)

        def lookup(action):
            adapter = self.adapters[action["adapter_id"]]
            if not adapter.authorized(project, user):
                return [], "inaccessible"
            ref = sha256(json.dumps(action, sort_keys=True).encode()).hexdigest()
            executed.add(ref)
            result = adapter.retrieve(
                project, action, timeout_seconds=max(0.01, timeout_seconds - (monotonic() - started))
            )
            items, denied = [], False
            for item in result:
                item = item.model_copy(
                    update={
                        "adapter_id": adapter.adapter_id,
                        "observed_at": item.observed_at or now(),
                        "retrieval_action_ref": ref,
                        "retrieval_action_refs": [ref],
                    }
                )
                if not permitted(item, project, user):
                    denied = True
                    item = item.model_copy(update={"content": "", "access_status": "revoked"})
                items.append(item)
            return items, "inaccessible" if denied else None

        pending = {pool.submit(lookup, action): action for action in actions}
        completed, unfinished = (
            wait(pending, timeout=max(0.01, timeout_seconds)) if pending else (set(), set())
        )
        items, failures = {}, []
        for future in completed:
            action = pending[future]
            try:
                found, error = future.result()
                for item in found:
                    key = evidence_id(item)
                    refs = sorted(
                        set(item.retrieval_action_refs + getattr(items.get(key), "retrieval_action_refs", []))
                    )
                    items[key] = item.model_copy(
                        update={
                            "retrieval_action_refs": refs,
                            "retrieval_action_ref": refs[0] if refs else None,
                        }
                    )
                if error:
                    failures.append(
                        {
                            "source": action["adapter_id"],
                            "reason": error,
                            "action_ref": sha256(json.dumps(action, sort_keys=True).encode()).hexdigest(),
                            "executed": sha256(json.dumps(action, sort_keys=True).encode()).hexdigest()
                            in executed,
                        }
                    )
            except Exception:
                failures.append(
                    {
                        "source": action["adapter_id"],
                        "reason": "unavailable",
                        "action_ref": sha256(json.dumps(action, sort_keys=True).encode()).hexdigest(),
                        "executed": sha256(json.dumps(action, sort_keys=True).encode()).hexdigest()
                        in executed,
                    }
                )
        for future in unfinished:
            future.cancel()
            ref = sha256(json.dumps(pending[future], sort_keys=True).encode()).hexdigest()
            failures.append(
                {
                    "source": pending[future]["adapter_id"],
                    "reason": "budget",
                    "action_ref": ref,
                    "executed": ref in executed,
                }
            )
        pool.shutdown(wait=False, cancel_futures=True)
        return [items[k] for k in sorted(items)], sorted(
            failures, key=lambda x: (x["source"], x["reason"], x.get("action_ref", ""))
        )


class KnowledgeCopies:
    def __init__(self, storage):
        self.storage = storage

    def reconcile(
        self, project_id, domain, incoming, *, approve=False, actor="system", expected_fingerprint=None
    ):
        project = self.storage.load_project(project_id)
        if approve and actor != "local":
            raise PermissionError("Only an authenticated user can approve a material knowledge update")
        if incoming.scope != "organization":
            return incoming, "reference"
        with self.storage.transaction(project_id):
            items = self.storage.load_context(project_id, domain)
            old = next((item for item in items if identity(item) == identity(incoming)), None)
            if (
                expected_fingerprint is not None
                and (sha256(old.model_dump_json().encode()).hexdigest() if old else "absent")
                != expected_fingerprint
            ):
                raise ValueError("Knowledge copy changed; compare the latest copy before approval")
            authorized = permitted(incoming, project)
            if not authorized:
                if old:
                    revoked = old.model_copy(update={"access_status": "revoked"})
                    self.storage.replace_context(
                        project_id, domain, [revoked if identity(i) == identity(old) else i for i in items]
                    )
                    self._record(project_id, old, incoming, "revoked", actor)
                return None, "inaccessible"
            if (
                old
                and old.source_version == incoming.source_version
                and old.content == incoming.content
                and old.access_status == incoming.access_status
            ):
                # Access restrictions are checked against the current source, even at the same version.
                if (
                    old.allowed_users == incoming.allowed_users
                    and old.allowed_projects == incoming.allowed_projects
                ):
                    return old, "stable"

            def normalize(text):
                return re.sub(r"[\s*_`#]+", "", text)

            low_risk = bool(
                old
                and not old.project_customized
                and incoming.evidence_status == "verified"
                and incoming.applicability == old.applicability
                and normalize(old.content) == normalize(incoming.content)
            )
            if old and not low_risk and not approve:
                for prior in self.storage.list_context_runs(project_id):
                    before, after = prior.get("previous"), prior.get("incoming")
                    if (
                        prior.get("kind") == "knowledge_update"
                        and prior.get("decision") == "review_required"
                        and before
                        and after
                    ):
                        same = (
                            identity(ContextItem.model_validate(after)) == identity(incoming)
                            and after.get("source_version") == incoming.source_version
                            and after["content"] == incoming.content
                            and before["content"] == old.content
                            and before.get("source_version") == old.source_version
                        )
                        if same and prior.get("review_outcome") != "approved":
                            disposition = (
                                "review_rejected"
                                if prior.get("review_outcome") == "rejected"
                                else "review_required"
                            )
                            return old.model_copy(
                                update={
                                    "conflict": f"Source update {prior['record_id']} was not adopted; retained project copy"
                                }
                            ), disposition
                record_id = self._record(project_id, old, incoming, "review_required", actor)
                return old.model_copy(
                    update={
                        "conflict": f"Source update {record_id} requires reconciliation; retained project copy"
                    }
                ), "review_required"
            adopted = incoming.model_copy(deep=True)
            adopted.copied_at = now()
            adopted.origin = incoming.original_uri or incoming.origin or incoming.source
            adopted.derived_version = old.derived_version + 1 if old else 1
            adopted.lineage = list(
                dict.fromkeys(
                    (old.lineage if old else [])
                    + [f"{identity(incoming)}:{incoming.source_version or 'unknown'}"]
                )
            )
            self._record(
                project_id,
                old,
                adopted,
                "approved" if approve else "auto_adopted" if old else "inherited",
                actor,
            )
            self.storage.replace_context(
                project_id, domain, [i for i in items if identity(i) != identity(adopted)] + [adopted]
            )
            return adopted, "adopted"

    def _record(self, project_id, old, incoming, decision, actor):
        record_id = uid()
        self.storage.save_context_run(
            project_id,
            record_id,
            {
                "kind": "knowledge_update",
                "record_id": record_id,
                "domain": incoming.domain.value if incoming.domain else "ORGANIZATION",
                "decision": decision,
                "actor": actor,
                "time": now().isoformat(),
                "previous": old.model_dump(mode="json") if old else None,
                "incoming": incoming.model_dump(mode="json"),
            },
        )
        self.storage.append_event(
            project_id,
            {
                "kind": "knowledge_update",
                "record_id": record_id,
                "decision": decision,
                "actor": actor,
                "time": now().isoformat(),
            },
        )
        return record_id

    def review(self, project_id, record_id, approve, actor="local", expected_fingerprint=None):
        if actor != "local":
            raise PermissionError("Only an authenticated user can review a knowledge update")
        record = self.storage.load_context_run(project_id, record_id)
        if record.get("kind") != "knowledge_update" or record.get("decision") != "review_required":
            raise ValueError("No reviewable knowledge update")
        if record.get("review_outcome"):
            return record
        if approve:
            incoming = ContextItem.model_validate(record["incoming"])
            project = self.storage.load_project(project_id)
            current = next(
                (
                    i
                    for i in self.storage.load_context(project_id, record["domain"])
                    if identity(i) == identity(incoming)
                ),
                None,
            )
            if not permitted(incoming, project) or current is not None and not permitted(current, project):
                raise PermissionError("Source access was revoked")
            self.reconcile(
                project_id,
                record["domain"],
                incoming,
                approve=True,
                actor=actor,
                expected_fingerprint=expected_fingerprint,
            )
        record.update(
            review_outcome="approved" if approve else "rejected",
            reviewed_by=actor,
            reviewed_at=now().isoformat(),
        )
        with self.storage.transaction(project_id):
            self.storage.save_context_run(project_id, record_id, record)
        return record
