# Sentinel Guarded Ops, CrewAI Marketplace Template

**Title:** Sentinel Guarded Ops
**Category:** Security & Compliance
**Type:** Crew (classic Python/YAML layout, per `crewAIInc/marketplace-crew-template`)
**Author:** Aridon (Triple R Restoration, LLC dba Aridon)
**License:** MIT

**Sentinel is the action-control platform for AI agents.**

- **Live demo:** https://aridon-v02.vercel.app/sentinel-demo
- **Paper:** Sentinel and NetGuard design paper, Zenodo,
  https://doi.org/10.5281/zenodo.23920785
- **MCP server:** https://github.com/jimrusk/sentinel-mcp

## Description

A CrewAI crew whose every consequential action passes through **Sentinel**,
Aridon's pre-execution authorization layer for AI agents, **before** it
executes. Sentinel returns **allow**, **hold** (a human must approve first),
or **deny**, and records every decision in a SHA-256 hash-chained audit log.

The crew's Operations Action Specialist processes three sample actions, a
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

**Stage and results:** In Sentinel's internal test harness (Sep 2026,
internal synthetic testing): 18/18 scenarios passed, 13 hostile actions held
before execution, 0 false positives. Sentinel is in early access, and we are
opening design-partner pilot conversations now. The evaluation has not had
an independent penetration test and carries no SOC 2 certification. Every
execution in this template is a mock.

Metadata for the submission form also lives in [`template.json`](template.json).
The crew itself (installation, configuration, usage, limitations) is
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
            └── guarded_actions.py  (execute_guarded_action, gate-enforced mock executor)
```

## How to submit to the CrewAI Marketplace

Per the instructions at https://marketplace.crewai.com (checked 2026-11-02):

1. Fork the official template repository that matches the use case:
   for a crew, `crewAIInc/marketplace-crew-template` (this project already
   follows its structure).
2. Push your template to GitHub.
3. If the repository is private, grant access to `crewAIEngineering`.
4. Fill out the submission form linked from marketplace.crewai.com
   ("Submit Your Crew or Flow") with your details and the GitHub URL of the
   template.
5. Review: initial screening (1–3 days), technical review (1–2 weeks),
   possible feedback, final decision. Submission is free.

**Status:** this repository is public on GitHub, and the template has been
submitted to the CrewAI Marketplace. See BUILD-REPORT.md for the build and
verification record.

## Production note

The gate in this template is a self-contained local port so the template runs
anywhere with no Sentinel account. In production, point the same tool
contract at the **Sentinel MCP server** (`@aridon/sentinel-mcp`) or the hosted
Sentinel service, where durable audit storage, policy management, and the
human approval workflow live.
