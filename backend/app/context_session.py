from .model_gateway import estimate_tokens


class ContextSessionService:
    def __init__(self, storage, settings, memory):
        self.storage = storage
        self.settings = settings
        self.memory = memory
        self.thresholds = (0.60, 0.75, 0.85)

    def append(self, project_id, role, content, metadata=None):
        session = self.storage.load_session(project_id)
        message = {"role": role, "content": content}
        if metadata:
            message.update({key: metadata[key] for key in ("origin", "provider", "model") if key in metadata})
        session["messages"].append(message)
        session["working_messages"].append(message)
        self.storage.save_session(project_id, session)

    def status(self, project_id):
        session = self.storage.load_session(project_id)
        profile = self.settings.current().capabilities
        usable = max(1, int(profile.context_window * 0.95) - profile.max_output_tokens)
        tokens = estimate_tokens([session.get("working_messages", []), session.get("active_context", {})])
        ratio = tokens / usable
        band = (
            "healthy"
            if ratio <= self.thresholds[0]
            else "watch"
            if ratio <= self.thresholds[1]
            else "compact_recommended"
            if ratio <= self.thresholds[2]
            else "high_pressure"
        )
        return {
            "used_tokens": tokens,
            "usable_context": usable,
            "model_context_window": profile.context_window,
            "usage_percent": round(100 * ratio, 1),
            "band": band,
            "estimated": True,
            "active_domains": session.get("active_domains", []),
            "compactions": session["compactions"],
            "model": self.settings.current().default_model,
            "provider": self.settings.current().provider,
        }

    def compact(self, project_id):
        # Called within a service transaction or explicit compact action transaction.
        state = self.storage.load_state(project_id)
        self.storage.save_state(project_id, state)
        memory = self.storage.load_memory(project_id)
        self.storage.save_memory(project_id, memory)
        session = self.storage.load_session(project_id)
        pending = next((m for m in reversed(session["working_messages"]) if m["role"] == "user"), None)
        summary = {"role": "system", "content": "Project continuity summary:\n" + memory.content[:2000]}
        session["working_messages"] = [summary] + ([pending] if pending else [])
        session["compactions"] += 1
        session["compaction_notice"] = (
            "Working context compacted. Project state, memory and artifacts preserved."
        )
        self.storage.save_session(project_id, session)
        return self.status(project_id)

    def prepare(self, state, package):
        session = self.storage.load_session(state.project_id)
        session["active_context"] = package.model_dump(mode="json")
        session["active_domains"] = [
            domain
            for domain, field in (
                ("BUSINESS", "business_context"),
                ("SAP", "sap_context"),
                ("ORGANIZATION", "organization_context"),
                ("HISTORICAL_DEVELOPMENT", "historical_context"),
                ("SDLC", "sdlc_context"),
            )
            if getattr(package, field)
        ]
        self.storage.save_session(state.project_id, session)
        status = self.status(state.project_id)
        if status["band"] == "high_pressure":
            self.compact(state.project_id)
