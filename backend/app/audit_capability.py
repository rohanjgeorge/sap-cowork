"""Structured audit workflow; findings never approve code or change progression."""

from dataclasses import dataclass, field
from typing import TypedDict
import re

from langgraph.graph import START, END, StateGraph
from langgraph.runtime import Runtime

from .context_planning import items


class AuditCursor(TypedDict):
    task_id: str


@dataclass
class AuditInvocation:
    request: object
    evidence: list = field(default_factory=list)
    code: str = ""
    findings: list = field(default_factory=list)
    result: object = None
    model_response: object = None


class AuditSubgraph:
    def __init__(self, report_worker):
        self.report_worker = report_worker
        graph = StateGraph(AuditCursor, context_schema=AuditInvocation)
        nodes = {
            "load_code_design_standards": self.load_code_design_standards,
            "run_structural_static_checks": self.run_structural_static_checks,
            "run_coding_standard_checks": self.run_coding_standard_checks,
            "run_security_performance_checks": self.run_security_performance_checks,
            "check_requirement_design_traceability": self.check_requirement_design_traceability,
            "model_assisted_semantic_review": self.model_assisted_semantic_review,
            "aggregate_findings": self.aggregate_findings,
            "return_audit_result": self.return_audit_result,
        }
        for name, fn in nodes.items():
            graph.add_node(name, fn)
        sequence = [START, *nodes, END]
        for a, b in zip(sequence, sequence[1:]):
            graph.add_edge(a, b)
        self.graph = graph.compile(checkpointer=False)

    def invoke(self, request):
        ctx = AuditInvocation(request.model_copy(deep=True))
        self.graph.invoke({"task_id": request.task_id}, context=ctx, durability="exit")
        if ctx.model_response:
            gateway = self.report_worker.worker.gateway
            gateway.last_response, gateway.last_task_id = ctx.model_response, request.task_id
        return ctx.result

    def finding(self, ctx, code, severity, message, sources=None):
        ctx.findings.append(
            {
                "code": code,
                "severity": severity,
                "message": message,
                "source_refs": sources or [],
                "evidence_status": "supported" if sources else "unknown",
            }
        )

    def load_code_design_standards(self, cursor, runtime: Runtime[AuditInvocation]):
        ctx = runtime.context
        ctx.evidence = items(ctx.request.context)
        ctx.code = "\n".join(i.content for i in ctx.evidence if i.source.startswith("artifact:ABAP:"))
        return {}

    def run_structural_static_checks(self, cursor, runtime: Runtime[AuditInvocation]):
        ctx = runtime.context
        if not ctx.code.strip():
            self.finding(
                ctx,
                "CODE_NOT_AVAILABLE",
                "warning",
                "Selected code evidence is unavailable; no static correctness claim can be made.",
            )
        elif "demonstration stub" in ctx.code.lower() or "TODO:" in ctx.code:
            self.finding(
                ctx,
                "INCOMPLETE_IMPLEMENTATION",
                "warning",
                "Selected code contains a demonstration marker or TODO; implementation review is required.",
                [i.source for i in ctx.evidence if i.source.startswith("artifact:ABAP:")],
            )
        self.finding(
            ctx,
            "STATIC_ANALYZER_NOT_CONFIGURED",
            "information",
            "No SAP compiler, ATC or syntax-check adapter is configured by this audit. Text checks are not executable validation.",
        )
        return {}

    def run_coding_standard_checks(self, cursor, runtime: Runtime[AuditInvocation]):
        ctx = runtime.context
        standards = [i for i in ctx.evidence if str(i.domain) == "STANDARDS_GOVERNANCE"]
        if not standards:
            self.finding(
                ctx,
                "STANDARDS_UNAVAILABLE",
                "warning",
                "Organization coding standards were not supplied; compliance cannot be confirmed.",
            )
        elif any(i.evidence_status in ("unknown", "disputed") for i in standards):
            self.finding(
                ctx,
                "STANDARDS_QUALIFIED",
                "warning",
                "Standards evidence is uncertain or disputed; resolve before claiming compliance.",
                [i.source for i in standards],
            )
        return {}

    def run_security_performance_checks(self, cursor, runtime: Runtime[AuditInvocation]):
        ctx = runtime.context
        if re.search(r"\bEXEC\s+SQL\b|CALL\s+FUNCTION\s+\(", ctx.code, re.I):
            self.finding(
                ctx,
                "DYNAMIC_OR_NATIVE_OPERATION",
                "warning",
                "Selected excerpt contains a native SQL or dynamic call pattern. Review input handling, authorization and execution context; this is a review lead, not a proven vulnerability.",
                [i.source for i in ctx.evidence if i.source.startswith("artifact:ABAP:")],
            )
        self.finding(
            ctx,
            "RUNTIME_CHECKS_NOT_RUN",
            "information",
            "Runtime security, performance and applicable test execution are not established by this report.",
        )
        return {}

    def check_requirement_design_traceability(self, cursor, runtime: Runtime[AuditInvocation]):
        ctx = runtime.context
        for kind in ("TDD", "FRD"):
            if not any(i.source.startswith(f"artifact:{kind}:") for i in ctx.evidence):
                self.finding(
                    ctx,
                    kind + "_TRACEABILITY_UNAVAILABLE",
                    "warning",
                    f"Selected {kind} evidence is unavailable; design/requirement traceability requires review.",
                )
        return {}

    def model_assisted_semantic_review(self, cursor, runtime: Runtime[AuditInvocation]):
        ctx = runtime.context
        # Reuse the bounded artifact worker through ModelGateway; it has no tools
        # or progression authority. Structured check results are trusted inputs.
        ctx.request.inputs = {
            **ctx.request.inputs,
            "instructions": ctx.request.inputs.get("instructions", "")
            + "\nReview these deterministic audit observations. Do not convert unknowns into passing checks, claim code execution or grant approval.\n"
            + "\n".join(f"{f['code']}: {f['message']}" for f in ctx.findings),
        }
        ctx.result = self.report_worker.invoke(ctx.request)
        ctx.model_response = self.report_worker.worker.gateway.last_response
        return {}

    def aggregate_findings(self, cursor, runtime: Runtime[AuditInvocation]):
        ctx = runtime.context
        ctx.result.output = {
            **(ctx.result.output or {}),
            "findings": ctx.findings,
            "audit_scope": "Selected context excerpts; no SAP execution or approval",
        }
        if ctx.result.output.get("artifact"):
            raw = ctx.result.output["artifact"]
            raw["validation_findings"] = ctx.findings
            raw["content"] += (
                "\n\nDeterministic audit findings (limited to selected evidence):\n"
                + "\n".join(f"- {f['code']} [{f['severity']}]: {f['message']}" for f in ctx.findings)
            )
        ctx.result.warnings = [f["message"] for f in ctx.findings if f["severity"] == "warning"]
        ctx.result.telemetry = {"audit_nodes": 8, "findings_count": len(ctx.findings), "sap_execution": False}
        return {}

    def return_audit_result(self, cursor, runtime: Runtime[AuditInvocation]):
        return {}
