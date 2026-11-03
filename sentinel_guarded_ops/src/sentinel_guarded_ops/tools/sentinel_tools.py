"""CrewAI tool wrappers around the Sentinel gate.

These mirror the three tools exposed by the Sentinel MCP server
(``sentinel_evaluate_action``, ``sentinel_audit_status``) so a CrewAI crew
can use the same evaluation contract. The evaluation itself lives in
``sentinel_gate.py``, a faithful port of the engine that ships in the MCP
server.
"""

import json
from typing import List, Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from . import sentinel_gate


class SentinelEvaluateActionInput(BaseModel):
    """Input schema for the Sentinel evaluation tool."""

    action: str = Field(
        ...,
        description=(
            "Plain-language description of what the agent proposes to do, "
            "including intent and target."
        ),
    )
    requested_actions: Optional[List[str]] = Field(
        default=None,
        description=(
            'Tool calls the agent wants to run, e.g. ["send email"], ["payment"], '
            '["database write"], ["credential access"]. Consequential actions are '
            "gated independently of content risk."
        ),
    )
    context: Optional[str] = Field(
        default=None,
        description=(
            'Authorization context, e.g. "Authorized blue-team incident response '
            'on our own environment."'
        ),
    )
    history: Optional[List[str]] = Field(
        default=None,
        description=(
            "Prior conversation turns; Sentinel scores escalation across turns, "
            "not just the latest request."
        ),
    )


class SentinelEvaluateActionTool(BaseTool):
    name: str = "sentinel_evaluate_action"
    description: str = (
        "Evaluate a proposed agent action against Sentinel policy BEFORE it "
        "executes. Returns a verdict of allow, hold (a human must approve "
        "first), or deny, with the risk score, the signals that fired, and "
        "reasons. Each evaluation is appended to a SHA-256 hash-chained "
        "audit log. Always run this before attempting any consequential "
        "action."
    )
    args_schema: Type[BaseModel] = SentinelEvaluateActionInput

    def _run(
        self,
        action: str,
        requested_actions: Optional[List[str]] = None,
        context: Optional[str] = None,
        history: Optional[List[str]] = None,
    ) -> str:
        result = sentinel_gate.evaluate_action(
            action=action,
            requested_actions=requested_actions,
            context=context or "",
            history=history,
        )
        return json.dumps(result, indent=2)


class SentinelAuditStatusTool(BaseTool):
    name: str = "sentinel_audit_status"
    description: str = (
        "Report the state of this process's Sentinel audit log: entry count, "
        "genesis and tip hashes, and a full SHA-256 chain re-verification. "
        "Use this when compiling the final report so the audit trail's "
        "integrity is on the record."
    )

    def _run(self) -> str:
        return json.dumps(sentinel_gate.audit_status(), indent=2)
