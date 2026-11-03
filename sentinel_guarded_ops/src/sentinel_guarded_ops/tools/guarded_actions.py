"""Guarded mock executors — the ONLY way this crew "does" anything.

Design rule of this template: agents never get a raw execution tool. The
single executor tool below re-runs the Sentinel evaluation internally before
touching anything, so even if the calling agent skips the standalone
``sentinel_evaluate_action`` step, no action executes without a gate verdict:

- verdict ``allow``  -> the mock action executes and a receipt is returned.
- verdict ``hold``   -> NOT executed. The action is surfaced as pending human
  approval, with the gate's reasons.
- verdict ``deny``   -> NOT executed. The action is surfaced as denied, with
  the gate's reasons.

The "execution" here is a mock: it appends a record to a process-local list
and returns a receipt string. It performs no real payment, sends no email,
and changes no system. Swap ``_mock_execute`` for a real integration only
behind the same gate.
"""

import json
from typing import List, Optional, Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from . import sentinel_gate

# Process-local record of mock executions, for the final report.
EXECUTED_ACTIONS: list[dict] = []

# The kinds of mock action this demo crew knows how to "perform".
ACTION_KINDS = ("report_summary", "vendor_payment", "config_change", "generic")


def _mock_execute(action_kind: str, action: str) -> dict:
    """Pretend to perform the action. No real-world side effects."""
    receipt = {
        "executed": True,
        "mock": True,
        "action_kind": action_kind,
        "action": action,
        "receipt": f"MOCK-{len(EXECUTED_ACTIONS) + 1:04d}",
    }
    EXECUTED_ACTIONS.append(receipt)
    return receipt


class ExecuteGuardedActionInput(BaseModel):
    """Input schema for the guarded executor tool."""

    action: str = Field(
        ...,
        description=(
            "Plain-language description of the exact action to perform, "
            "including intent and target. This text is what Sentinel evaluates."
        ),
    )
    action_kind: str = Field(
        ...,
        description=(
            "The kind of mock action: one of 'report_summary', "
            "'vendor_payment', 'config_change', or 'generic'."
        ),
    )
    requested_actions: Optional[List[str]] = Field(
        default=None,
        description=(
            'Tool calls this action needs, e.g. ["payment"], ["execute"], '
            '["network request"]. Consequential actions are gated '
            "independently of content risk."
        ),
    )
    context: Optional[str] = Field(
        default=None,
        description="Authorization context for the evaluation, if any.",
    )


class ExecuteGuardedActionTool(BaseTool):
    name: str = "execute_guarded_action"
    description: str = (
        "Perform an operations action, but ONLY after Sentinel authorizes it. "
        "This tool evaluates the action with Sentinel first: if the verdict is "
        "allow, the (mock) action executes and a receipt is returned; if the "
        "verdict is hold, the action is NOT executed and is reported as "
        "pending human approval; if the verdict is deny, the action is NOT "
        "executed and is reported as denied, with reasons. This is the only "
        "execution tool available to the crew."
    )
    args_schema: Type[BaseModel] = ExecuteGuardedActionInput

    def _run(
        self,
        action: str,
        action_kind: str,
        requested_actions: Optional[List[str]] = None,
        context: Optional[str] = None,
    ) -> str:
        # The gate runs here, inside the executor, unconditionally.
        evaluation = sentinel_gate.evaluate_action(
            action=action,
            requested_actions=requested_actions,
            context=context or "",
        )
        verdict = evaluation["verdict"]

        if verdict == "allow":
            kind = action_kind if action_kind in ACTION_KINDS else "generic"
            receipt = _mock_execute(kind, action)
            outcome = {
                "executed": True,
                "status": "EXECUTED (mock)",
                "receipt": receipt,
                "evaluation": evaluation,
            }
        elif verdict == "hold":
            outcome = {
                "executed": False,
                "status": "HELD — not executed. A human must approve this action first.",
                "evaluation": evaluation,
            }
        else:  # deny
            outcome = {
                "executed": False,
                "status": "DENIED — not executed. This action must not be performed.",
                "evaluation": evaluation,
            }
        return json.dumps(outcome, indent=2)
