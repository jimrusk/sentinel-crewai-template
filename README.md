# Sentinel Guarded Ops — CrewAI Marketplace Template

**Title:** Sentinel Guarded Ops
**Category:** Security & Compliance
**Type:** Crew (classic Python/YAML layout, per `crewAIInc/marketplace-crew-template`)
**Author:** Aridon (Triple R Restoration, LLC dba Aridon)
**License:** MIT

## Description

A CrewAI crew whose every consequential action passes through **Sentinel**,
Aridon's pre-execution authorization layer for AI agents, **before** it
executes. Sentinel returns **allow**, **hold** (a human must approve first),
or **deny**, and records every decision in a SHA-256 hash-chained audit log.

The crew's Operations Action Specialist processes three sample actions — a
benign report summary (allowed, executes), a vendor payment (held:
consequential actions need a human approver even at zero content risk), and a
simulated hostile request (denied, never executes). Its only execution tool
re-checks the gate internally, so held or denied actions cannot execute even
if the agent skips the pre-check step. A Compliance Reporter then verifies
the audit chain and writes the final report (`sentinel_gate_report.md`).

The evaluator is a faithful port of the exact engine that ships in the
Sentinel MCP server (weighted signal rules, 0–100 score, disposition bands,
an independent action gate, trajectory analysis, hash-chained audit), and the
included standalone test reproduces the MCP server's smoke-test results
exactly.

**Honest stage:** Sentinel is a development-stage technical preview,
validated in internal synthetic testing only (Sep 2026 harness: 18/18
scenarios, 13/13 hostile actions held pre-execution, 0 false positives). No
customers, no revenue, no independent penetration test, no SOC 2. Every
execution in this template is a mock.

Metadata for the submission form also lives in [`template.json`](template.json).
The crew itself — installation, configuration, usage, limitations — is
documented in [`sentinel_guarded_ops/README.md`](sentinel_guarded_ops/README.md).

## Repository layout

```
sentinel-crewai-template/
├── README.md                  <- this file (marketplace-facing)
├── template.json              <- marketplace metadata (name, description, category, inputs)
├── BUILD-REPORT.md            <- build + verification record
└── sentinel_guarded_ops/      <- the crew project (crewai create crew layout)
    ├── pyproject.toml
    ├── requirements.txt       (crewai pinned: 1.15.34)
    ├── knowledge/user_preference.txt
    ├── tests/test_sentinel_gate.py   (LLM-free gate verification)
    └── src/sentinel_guarded_ops/
        ├── main.py  crew.py
        ├── config/agents.yaml, config/tasks.yaml
        └── tools/
            ├── sentinel_gate.py    (ported Sentinel engine + audit chain)
            ├── sentinel_tools.py   (sentinel_evaluate_action, sentinel_audit_status)
            └── guarded_actions.py  (execute_guarded_action — gate-enforced mock executor)
```

## How to submit to the CrewAI Marketplace

Per the instructions at https://marketplace.crewai.com (checked 2026-11-02):

1. Fork the official template repository that matches the use case —
   for a crew, `crewAIInc/marketplace-crew-template` (this project already
   follows its structure).
2. Push your template to GitHub.
3. If the repository is private, grant access to `crewAIEngineering`.
4. Fill out the submission form linked from marketplace.crewai.com
   ("Submit Your Crew or Flow") with your details and the GitHub URL of the
   template.
5. Review: initial screening (1–3 days), technical review (1–2 weeks),
   possible feedback, final decision. Submission is free.

**This repository has NOT been pushed to GitHub and nothing has been
submitted.** Those steps require Aridon's GitHub account and a form
submission in Aridon's name — see BUILD-REPORT.md.

## Production note

The gate in this template is a self-contained local port so the template runs
anywhere with no Sentinel account. In production, point the same tool
contract at the **Sentinel MCP server** (`@aridon/sentinel-mcp`) or the hosted
Sentinel service, where durable audit storage, policy management, and the
human approval workflow live.
