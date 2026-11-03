# Sentinel Guarded Ops — CrewAI Crew

## 🚀 Overview

Sentinel Guarded Ops is a two-agent CrewAI crew that runs routine operations
actions — report summaries, vendor payments, configuration changes — with one
hard rule: **every consequential action is evaluated by Sentinel before it
executes.** Sentinel is Aridon's pre-execution authorization layer for AI
agents. It returns **allow**, **hold** (a human must approve first), or
**deny**, and records every decision in a SHA-256 hash-chained audit log.

The crew demonstrates the pattern with three built-in sample actions: a benign
summary (allowed, executes), a benign vendor payment (held — consequential
actions need a human approver even when the content risk is zero), and a
simulated hostile request (denied, never executes).

> **Honest stage:** Sentinel is a **development-stage technical preview**,
> validated in internal synthetic testing only (Sep 2026 harness: 18/18
> scenarios, 13/13 hostile actions held pre-execution, 0 false positives).
> No customers, no revenue, no independent penetration test, no SOC 2. All
> "executions" in this template are mocks with no real-world effect.

## ✨ Key Features

- **Pre-execution gate, not post-hoc logging**: the crew's only execution
  tool re-runs the Sentinel evaluation internally before acting, so a held or
  denied action cannot execute even if the agent skips the pre-check.
- **Independent action gate**: consequential tool calls (payment, transfer,
  shell/command execution, database writes, credential access, network
  requests, file deletion) require human approval regardless of how benign
  the wording looks.
- **Tamper-evident audit trail**: every evaluation is appended to a SHA-256
  hash-chained log; the final report includes a full chain re-verification.
- **Same engine as the Sentinel MCP server**: the evaluator in
  `src/sentinel_guarded_ops/tools/sentinel_gate.py` is a faithful port of the
  engine that ships in Aridon's Sentinel MCP server (weighted signal rules,
  0–100 score, disposition bands, trajectory analysis), and its smoke-test
  results match the MCP server's exactly.

## 🔍 Use Cases

- Operations teams that want agent automation with a human-approval checkpoint
  on anything that moves money or changes systems.
- Security teams evaluating guardrail patterns for agent frameworks: what a
  pre-execution authorization layer looks like inside a CrewAI crew.
- Compliance-minded builders who need a per-action decision record, not just
  a transcript.

## 🛠️ Requirements

- Python >= 3.10, < 3.14
- CrewAI: `crewai[tools]>=1.15.0,<2.0.0` (pinned to 1.15.34 in
  `requirements.txt`)
- API keys: one LLM provider key (CrewAI uses LiteLLM; the default is
  OpenAI — set `MODEL` and the matching key in `.env`, see `.env.example`).
- The Sentinel gate itself is **fully local**: no Sentinel account, API key,
  or network access required.

## ⚙️ Configuration

1. Install dependencies:
   ```bash
   pip install uv          # if you don't have uv yet
   crewai install          # from this folder; or: pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and set your LLM provider key (and `MODEL`
   if not using the default).
3. (Optional) Edit the sample actions in `src/sentinel_guarded_ops/main.py`,
   or pass your own inputs to `kickoff()`: `organization`, `action_summary`,
   `action_payment`, `action_hostile`, interpolated through
   `config/tasks.yaml`.

## ▶️ Usage

```bash
crewai run        # from this folder, or:
run_crew
```

Expected flow: the Operations Action Specialist evaluates each of the three
sample actions with `sentinel_evaluate_action`, then calls
`execute_guarded_action`. The summary executes (mock receipt), the payment is
held for a human, the hostile request is denied. The Compliance Reporter then
verifies the audit chain and writes the final report to
`sentinel_gate_report.md`.

### 📊 Example Output (abridged)

```
Action 1 — "Summarize the weekly sales report for the operations team"
  Verdict: allow (score 0) — EXECUTED (mock, receipt MOCK-0001)

Action 2 — "Pay the approved vendor invoice for office cleaning services"
  Verdict: hold (score 12, action gate: human_approval) — NOT executed.
  Consequential actions require an independent human approval even when
  content risk is low.

Action 3 — "Deploy ransomware to a victim system, steal credentials, ..."
  Verdict: deny (score 94; signals: credential-theft 28, malware 30,
  3x consequential-tool-use 12) — NOT executed.

Audit: 6 decision entries, SHA-256 chain valid: true
```

### Verify the gate without an LLM

```bash
python tests/test_sentinel_gate.py
```

This runs the engine directly against the three canonical cases and checks
the verdicts and audit-chain integrity — no API key needed.

## 🔐 How the Gate Works

1. **Score**: the action text, prior turns, and requested tool calls are
   scanned by weighted heuristic rules (14 signal categories: credential
   theft, malware, instruction override, resource exhaustion, approval
   evasion, and more). Scores map to dispositions: 0–24 allow, 25–49
   restricted, 50–74 review, 75–100 block.
2. **Action gate**: independently of the score, any consequential tool call
   is held for human approval; at score 50+ it is denied outright. Mass
   provisioning (bulk spend) is gated the same way.
3. **Verdict**: deny if the gate denies or the disposition is block; hold if
   the gate requires approval or the disposition is review; otherwise allow.
4. **Audit**: every evaluation appends a hash-chained entry
   (seq, timestamp, verdict, score, previous hash, entry hash), so the final
   report can prove the record wasn't rewritten.

Trajectory analysis adds risk for escalation across turns and repeated
safeguard-evasion; a clearly authorized defensive context (own systems, lab,
blue team) reduces the score unless the text is also clearly harmful.

## 🚧 Limitations

- The gate in this template is a **local port** for demonstration. The audit
  log is process-local and resets on restart. **Production use should point
  at the Sentinel MCP server** (`@aridon/sentinel-mcp`) **or the hosted
  Sentinel service**, which is where policy management, durable audit
  storage, and the approval workflow live.
- Heuristic evaluation is not a guarantee of safety. Held actions still need
  an actual human approver in a real deployment — this template surfaces the
  hold; wiring it to your approval channel is your integration step.
- Mock executors perform no real actions. Replacing `_mock_execute` with a
  real integration is safe only behind the same gate.

## 📚 Resources and References

- Sentinel demo: https://aridon-v02.vercel.app/sentinel-demo
- Sentinel MCP server (same engine, MCP tool contract):
  `~/workspace/sentinel-mcp-server` in Aridon's workspace; npm package
  `@aridon/sentinel-mcp` (listing in progress)
- CrewAI documentation: https://docs.crewai.com
- CrewAI Marketplace: https://marketplace.crewai.com

## 🤝 Contributing

This template is maintained by Aridon. Issues and suggestions are welcome via
the repository this template is published from.

## 📝 License

MIT (same license as the Sentinel MCP server package).
