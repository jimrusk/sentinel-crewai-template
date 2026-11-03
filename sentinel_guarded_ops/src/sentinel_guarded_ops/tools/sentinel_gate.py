"""Sentinel evaluation gate — Python port of Aridon's Sentinel engine.

This module is a faithful port of the exact code that ships in the Sentinel
MCP server (``~/workspace/sentinel-mcp-server``):

- The heuristic engine is ported from ``src/sentinel.ts``, which was itself
  ported verbatim from ``aridon-app/lib/sentinel-grid.ts`` (the real
  ``analyzeSentinel`` engine: weighted signal rules, 0-100 score, disposition
  bands, an independent action gate, and trajectory analysis).
- The audit log is ported from ``src/audit.ts``, itself ported verbatim from
  ``aridon-app/lib/sentinelAudit.ts`` (SHA-256 hash-chained, append-only).

Do not fork the logic here; changes should land in aridon-app first and be
re-ported. Rule patterns, weights, thresholds, and gate behavior below match
the TypeScript originals exactly (including JS ``Math.round`` half-up
semantics, which differ from Python's banker's rounding).

Honest stage: Sentinel is a development-stage technical preview, validated in
internal synthetic testing only. This module is a local demonstration gate for
the template; production use should point at the Sentinel MCP server or the
hosted Sentinel service.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Evaluation engine (port of src/sentinel.ts / aridon-app lib/sentinel-grid.ts)
# ---------------------------------------------------------------------------

# Dispositions: 'allow' | 'restricted' | 'review' | 'block'
# Signal sources: 'prompt' | 'history' | 'action' | 'provider'


def _rule(category: str, weight: int, reason: str, pattern: str) -> dict:
    return {
        "category": category,
        "weight": weight,
        "reason": reason,
        "pattern": re.compile(pattern, re.IGNORECASE),
    }


RULES = [
    _rule("safeguard-evasion", 18, "Attempts to bypass, disable, or conceal safety controls.",
          r"\b(bypass|disable|evade|jailbreak|ignore\s+(the\s+)?(rules|policy|safety)|hide\s+(my\s+)?intent|avoid\s+detection)\b"),
    _rule("credential-theft", 28, "Seeks credentials, secrets, tokens, or account access.",
          r"\b(steal|harvest|capture|exfiltrate)\b.{0,40}\b(passwords?|credentials?|tokens?|cookies?|api\s*keys?|sessions?|secrets?)\b"),
    _rule("phishing-social-engineering", 22, "Potential credential phishing or deceptive impersonation behavior.",
          r"\b(phish|phishing|credential\s+page|fake\s+login|impersonat(e|ion))\b"),
    _rule("intrusion-exploitation", 24, "Potential unauthorized intrusion or exploit activity.",
          r"\b(exploit|remote\s+code\s+execution|privilege\s+escalation|lateral\s+movement|persistence|initial\s+access)\b"),
    _rule("malware", 30, "Potential malware, ransomware, credential stealer, or destructive payload behavior.",
          r"\b(ransomware|credential\s+stealer|keylogger|malware|botnet|wipe\s+(the\s+)?disk|encrypt\s+victim)\b"),
    _rule("data-exfiltration", 26, "Potential unauthorized extraction or transfer of protected data.",
          r"\b(exfiltrat(e|ion)|dump\s+(the\s+)?database|steal\s+(customer|user|private)\s+data)\b"),
    _rule("reconnaissance", 10, "Reconnaissance language warrants context-sensitive review.",
          r"\b(scan|enumerate|recon|find\s+vulnerabilit|attack\s+surface)\b"),
    _rule("obfuscation", 10, "Obfuscation can be a signal when combined with other risky behavior.",
          r"\b(obfuscat(e|ion)|encode\s+to\s+evade|polymorphic|undetectable)\b"),
    # v0.2.1: resource-exhaustion / anomalous-spend coverage. Mass provisioning
    # is a critical attack primitive against self-funding agents: a compromised
    # agent can burn its treasury on infrastructure without any fund transfer.
    _rule("resource-exhaustion", 35, "Bulk resource provisioning or mass creation request that could exhaust budget or capacity.",
          r"\b(spin\s*up|provision|deploy|launch|stand\s*up|create)\b[^.\n]{0,60}\b(\d{2,}|hundreds?|thousands?|dozens?)\b[^.\n]{0,60}\b(vms?|virtual\s+machines?|instances?|servers?|nodes?|containers?|pods?|workers?|gpus?|clusters?)\b"),
    _rule("approval-evasion", 25, "Explicit request to skip or bypass approval, authorization, or oversight.",
          r"\b(skip|bypass(?:ing)?|without|no)\b[^.\n]{0,30}\b(all\s+)?(approvals?|authori[sz]ations?|oversight|human\s+review|permission)\b"),
    _rule("treasury-drain", 15, "Request to move an entire treasury balance or all available funds at once.",
          r"\b(entire|whole|full|all)\b[^.\n]{0,30}\b(treasury|treasuries|balances?|funds?|accounts?|wallets?)\b|\b(drain|empty)\b[^.\n]{0,20}\b(treasury|account|wallet|funds?)\b|\btransfer\b[^.\n]{0,30}\b(everything|all\s+of\s+it)\b"),
    _rule("urgency-pressure", 5, "Urgency or time-pressure language; a weak signal that matters mainly combined with other risk.",
          r"\b(immediately|right\s*now|urgent(ly)?|asap|a\.s\.a\.p\.)\b"),
    # v0.2.2: instruction-override / prompt-injection structure. The classic
    # "ignore all previous instructions" family targets the agent's instruction
    # hierarchy itself rather than naming a malicious payload, so payload-based
    # rules miss it. This is the primary attack shape against comment-triggered
    # automations (e.g. hijacking a comment-to-DM bot).
    _rule("instruction-override", 30, "Attempts to override, replace, or discard prior instructions (prompt-injection structure).",
          r"\b(ignore|disregard|forget|override|discard)\b[^.\n]{0,40}\b(previous|prior|earlier|all|your|system)\b[^.\n]{0,40}\b(instructions?|directives?|system\s+prompt|prompts?)\b|\bhere\s+are\s+your\s+new\s+(instructions?|directives?)\b"),
]

AUTHORIZED_CONTEXT = re.compile(
    r"\b(authorized|permission|owned\s+system|my\s+system|lab|sandbox|ctf|capture\s+the\s+flag|training\s+environment|defensive|blue\s+team|incident\s+response|security\s+audit|penetration\s+test)\b",
    re.IGNORECASE,
)
CLEARLY_HARMFUL = re.compile(
    r"\b(victim|without\s+permission|unauthorized|steal|ransomware|credential\s+stealer|exfiltrate)\b",
    re.IGNORECASE,
)
HIGH_IMPACT_ACTION = re.compile(
    r"\b(shell|command|execute|deploy|send\s+email|http\s+request|network\s+request|database\s+(write|delete|update)|delete\s+file|credential\s+access|secret\s+access|payment|transfer)\b",
    re.IGNORECASE,
)
# v0.2.1: provisioning verbs. A bare "provision 1 server" is routine and must
# NOT trip the gate on its own — it only becomes consequential when paired
# with a fired resource-exhaustion signal (mass scale described in the text).
PROVISIONING_ACTION = re.compile(r"\b(provision|spin\s*up|deploy|launch|stand\s*up)\b", re.IGNORECASE)


def _js_round(value: float) -> int:
    """JavaScript Math.round semantics (half rounds up), unlike Python round()."""
    return math.floor(value + 0.5)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def _scan(text: str, source: str, multiplier: float = 1.0) -> list[dict]:
    return [
        {
            "category": rule["category"],
            "weight": _js_round(rule["weight"] * multiplier),
            "reason": rule["reason"],
            "source": source,
        }
        for rule in RULES
        if rule["pattern"].search(text)
    ]


def _disposition_for(score: int) -> str:
    if score >= 75:
        return "block"
    if score >= 50:
        return "review"
    if score >= 25:
        return "restricted"
    return "allow"


def analyze_sentinel(
    prompt: str,
    history: Optional[list[str]] = None,
    requested_actions: Optional[list[str]] = None,
    provider_signals: Optional[list[dict]] = None,
    authorization_context: str = "",
) -> dict:
    """Port of analyzeSentinel() from the Sentinel engine. Returns the same
    assessment shape as the TypeScript original."""
    prompt = (prompt or "").strip()
    history = [h for h in (history or []) if h][-12:]
    actions = [a for a in (requested_actions or []) if a][:20]
    auth_context = authorization_context or ""

    prompt_signals = _scan(prompt, "prompt", 1)
    history_signals: list[dict] = []
    for index, turn in enumerate(history):
        age = len(history) - index
        multiplier = 0.65 if age <= 2 else 0.4
        history_signals.extend(_scan(turn, "history", multiplier))

    action_signals = [
        {
            "category": "consequential-tool-use",
            "weight": 12,
            "reason": "A consequential external action was requested and must pass an independent action gate.",
            "source": "action",
        }
        for action in actions
        if HIGH_IMPACT_ACTION.search(action)
    ]

    provider_signal_list = [
        {
            "category": signal.get("category") or f"provider:{signal['provider']}",
            "weight": _js_round(_clamp(signal["score"], 0, 100) * 0.18),
            "reason": f"{signal['provider']} supplied an independent risk signal.",
            "source": "provider",
        }
        for signal in (provider_signals or [])[:8]
    ]

    all_signals = prompt_signals + history_signals + action_signals + provider_signal_list
    categories = {s["category"] for s in all_signals if s["source"] != "action"}

    current_risk = sum(s["weight"] for s in prompt_signals)
    historical_risk = sum(s["weight"] for s in history_signals)
    repeated_evasion = (
        len([t for t in [prompt, *history] if RULES[0]["pattern"].search(t)]) >= 2
    )
    escalation_detected = current_risk >= 24 and historical_risk >= 12

    score = sum(s["weight"] for s in all_signals)
    if repeated_evasion:
        score += 10
    if escalation_detected:
        score += 10
    if len(categories) >= 3:
        score += 8

    has_authorized_context = bool(AUTHORIZED_CONTEXT.search(f"{auth_context} {prompt}"))
    has_clearly_harmful_language = bool(CLEARLY_HARMFUL.search(prompt))
    if has_authorized_context and not has_clearly_harmful_language:
        score -= 18

    score = int(_clamp(_js_round(score), 0, 100))
    disposition = _disposition_for(score)

    high_impact_requested = any(HIGH_IMPACT_ACTION.search(a) for a in actions)
    # v0.2.1: bulk provisioning at mass scale is a consequential spend action
    # and must clear a human gate even when no fund transfer is involved. The
    # signal requirement keeps routine single-server provisioning out of the
    # gate.
    resource_exhaustion_signaled = any(
        s["category"] == "resource-exhaustion" for s in prompt_signals
    )
    bulk_provisioning_requested = resource_exhaustion_signaled and any(
        PROVISIONING_ACTION.search(a) for a in actions
    )
    consequential_requested = high_impact_requested or bulk_provisioning_requested
    gate_reasons: list[str] = []
    action_gate_mode = "pass"

    if consequential_requested and score >= 50:
        action_gate_mode = "deny"
        gate_reasons.append(
            "Risk is elevated and consequential external actions are blocked before execution."
        )
    elif consequential_requested:
        action_gate_mode = "human_approval"
        gate_reasons.append(
            "Consequential actions require an independent human approval even when content risk is low."
        )
    elif score >= 75:
        action_gate_mode = "deny"
        gate_reasons.append("Critical-risk content cannot proceed to tool execution.")
    if bulk_provisioning_requested:
        gate_reasons.append(
            "Bulk infrastructure provisioning at mass scale was detected; spend of this size needs a human approver."
        )

    external = provider_signals or []
    if external:
        avg: Optional[int] = _js_round(
            sum(_clamp(s["score"], 0, 100) for s in external) / len(external)
        )
        max_score: Optional[int] = int(max(_clamp(s["score"], 0, 100) for s in external))
    else:
        avg = None
        max_score = None

    reasons = list(dict.fromkeys(s["reason"] for s in all_signals))
    if has_authorized_context and not has_clearly_harmful_language:
        reasons.append(
            "Authorized defensive context reduced risk, but did not disable safety checks."
        )
    if not reasons:
        reasons.append(
            "No material malicious-intent indicators were detected in the supplied context."
        )

    return {
        "score": score,
        "disposition": disposition,
        "reasons": reasons,
        "signals": all_signals,
        "actionGate": {"mode": action_gate_mode, "reasons": gate_reasons},
        "trajectory": {
            "turnsAnalyzed": len(history) + 1,
            "escalationDetected": escalation_detected,
            "repeatedEvasionDetected": repeated_evasion,
            "categoryCount": len(categories),
        },
        "providerConsensus": {
            "providers": len(external),
            "averageScore": avg,
            "maxScore": max_score,
        },
        "privacy": {
            "rawPromptSharingRequired": False,
            "recommendation": (
                "Keep raw prompts with the originating provider. Share only minimized "
                "threat indicators, scores, technique tags, and confirmed campaign "
                "fingerprints across organizations."
            ),
        },
    }


def verdict_for(assessment: dict) -> str:
    """Map Sentinel's internal disposition + action gate to the public verdict.
    Identical to verdictFor() in the MCP server's src/index.ts."""
    if assessment["actionGate"]["mode"] == "deny" or assessment["disposition"] == "block":
        return "deny"
    if assessment["actionGate"]["mode"] == "human_approval" or assessment["disposition"] == "review":
        return "hold"
    return "allow"


# ---------------------------------------------------------------------------
# Audit log (port of src/audit.ts / aridon-app lib/sentinelAudit.ts)
#
# Tamper-evident append-only audit log. Every consequential Sentinel decision
# lands here as a hash-chained entry: each entry commits to the previous
# entry's hash, so any insertion, deletion, or edit anywhere in the history
# breaks the chain and verify() catches it.
# ---------------------------------------------------------------------------

SENTINEL_AUDIT_GENESIS_HASH = "0" * 64

AUDIT_EVENT_TYPES = (
    "decision",
    "approval",
    "override",
    "policy_change",
    "incident",
    "pentest_run",
    "chain_verification",
)


def _canonical_json(entry: dict) -> str:
    # Fixed key order so the hash is deterministic (mirrors canonicalJson()).
    return json.dumps(
        {
            "seq": entry["seq"],
            "ts": entry["ts"],
            "tenantId": entry["tenantId"],
            "actor": entry["actor"],
            "eventType": entry["eventType"],
            "summary": entry["summary"],
            "details": entry["details"],
            "prevHash": entry["prevHash"],
        },
        separators=(",", ":"),
        ensure_ascii=False,
    )


def hash_audit_entry(entry: dict) -> str:
    return hashlib.sha256(_canonical_json(entry).encode("utf-8")).hexdigest()


def _iso_now() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class SentinelAuditLog:
    """Port of the SentinelAuditLog class from the TypeScript audit module."""

    def __init__(self) -> None:
        self._entries: list[dict] = []

    @property
    def size(self) -> int:
        return len(self._entries)

    def append(
        self,
        tenant_id: str,
        actor: str,
        event_type: str,
        summary: str,
        details: Optional[dict] = None,
    ) -> dict:
        prev = self._entries[-1] if self._entries else None
        base = {
            "seq": len(self._entries) + 1,
            "ts": _iso_now(),
            "tenantId": tenant_id,
            "actor": actor,
            "eventType": event_type,
            "summary": summary,
            "details": details if details is not None else {},
            "prevHash": prev["hash"] if prev else SENTINEL_AUDIT_GENESIS_HASH,
        }
        entry = {**base, "hash": hash_audit_entry(base)}
        self._entries.append(entry)
        return entry

    def verify(self) -> dict:
        """Recompute every link in the chain. Any tampering breaks verification."""
        prev_hash = SENTINEL_AUDIT_GENESIS_HASH
        for entry in self._entries:
            if entry["prevHash"] != prev_hash:
                return {
                    "ok": False,
                    "checked": len(self._entries),
                    "brokenAtSeq": entry["seq"],
                    "reason": f"prevHash mismatch at seq {entry['seq']}: chain link broken",
                }
            rest = {k: v for k, v in entry.items() if k != "hash"}
            if hash_audit_entry(rest) != entry["hash"]:
                return {
                    "ok": False,
                    "checked": len(self._entries),
                    "brokenAtSeq": entry["seq"],
                    "reason": f"hash mismatch at seq {entry['seq']}: entry content was altered",
                }
            prev_hash = entry["hash"]
        return {
            "ok": True,
            "checked": len(self._entries),
            "tipHash": self._entries[-1]["hash"] if self._entries else SENTINEL_AUDIT_GENESIS_HASH,
        }

    def record_verification(self, tenant_id: str, actor: str) -> dict:
        """Record a verification pass itself, so audits of the audit trail are visible."""
        verification = self.verify()
        entry = self.append(
            tenant_id=tenant_id,
            actor=actor,
            event_type="chain_verification",
            summary=(
                f"Audit chain verified: {verification['checked']} entries intact"
                if verification["ok"]
                else f"Audit chain verification FAILED at seq {verification.get('brokenAtSeq')}"
            ),
            details={"verification": verification},
        )
        return {"entry": entry, "verification": verification}

    def list(self) -> list[dict]:
        return list(self._entries)

    def export_json(self) -> str:
        return json.dumps(
            {"exportedAt": _iso_now(), "entries": self._entries}, indent=2
        )


# ---------------------------------------------------------------------------
# Shared gate used by the CrewAI tools in this template.
#
# Mirrors the MCP server: one process-local audit log, tenant "mcp-local"
# there, "crewai-template" here. The log resets when the process restarts;
# the full product persists entries. Production use should point at the
# Sentinel MCP server or the hosted Sentinel service instead of this port.
# ---------------------------------------------------------------------------

TENANT = "crewai-template"
ACTOR = "sentinel-crewai-template"

AUDIT_LOG = SentinelAuditLog()

PREVIEW_NOTE = (
    "Development-stage technical preview. Heuristic evaluation only; "
    "not a guarantee of safety."
)


def evaluate_action(
    action: str,
    requested_actions: Optional[list[str]] = None,
    context: str = "",
    history: Optional[list[str]] = None,
) -> dict:
    """Evaluate a proposed agent action BEFORE execution.

    Same behavior as the MCP server's ``sentinel_evaluate_action`` tool:
    returns a verdict of allow / hold / deny with score, disposition, signals
    and reasons, and appends a ``decision`` entry to the hash-chained audit
    log, returning its seq/hash.
    """
    assessment = analyze_sentinel(
        prompt=action,
        requested_actions=requested_actions,
        authorization_context=context,
        history=history,
    )
    verdict = verdict_for(assessment)
    entry = AUDIT_LOG.append(
        tenant_id=TENANT,
        actor=ACTOR,
        event_type="decision",
        summary=(
            f"CrewAI template evaluation: verdict={verdict} "
            f"score={assessment['score']} disposition={assessment['disposition']}"
        ),
        details={
            "verdict": verdict,
            "score": assessment["score"],
            "disposition": assessment["disposition"],
            "gate": assessment["actionGate"]["mode"],
        },
    )
    return {
        "verdict": verdict,
        "disposition": assessment["disposition"],
        "restricted": assessment["disposition"] == "restricted",
        "score": assessment["score"],
        "reasons": assessment["reasons"],
        "signals": assessment["signals"],
        "actionGate": assessment["actionGate"],
        "trajectory": assessment["trajectory"],
        "audit": {"seq": entry["seq"], "hash": entry["hash"], "prevHash": entry["prevHash"]},
        "note": PREVIEW_NOTE,
    }


def audit_status() -> dict:
    """Same shape as the MCP server's ``sentinel_audit_status`` tool."""
    verification = AUDIT_LOG.verify()
    result: dict[str, Any] = {
        "entries": AUDIT_LOG.size,
        "genesisHash": SENTINEL_AUDIT_GENESIS_HASH,
        "tipHash": verification.get("tipHash", SENTINEL_AUDIT_GENESIS_HASH),
        "chainValid": verification["ok"],
        "checked": verification["checked"],
        "persistence": "process-local (in memory); resets on process restart",
    }
    if not verification["ok"]:
        result["brokenAtSeq"] = verification.get("brokenAtSeq")
        result["reason"] = verification.get("reason")
    return result
