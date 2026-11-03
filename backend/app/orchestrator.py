"""Stable orchestration import; execution now runs through LangGraph.

The original runtime remains in legacy_orchestrator.py for parity tests and rollback.
"""

from .langgraph_orchestrator import LangGraphOrchestrator

Orchestrator = LangGraphOrchestrator

__all__ = ["Orchestrator"]
