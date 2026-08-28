# Phase 3: Agent Dependability & Safety - Execution Plans

This document provides a consolidated view of the execution plans for Phase 3. The actual plan files are located in `.planning/phases/03-agent-dependability-safety/`.

## Phase Goal
Safe, autonomous customer service with deterministic policy and human fallbacks.

## Wave Structure

| Wave | Plan | Objective | Autonomous |
|------|------|-----------|------------|
| 1 | [03-01](03-agent-dependability-safety/03-01-PLAN.md) | Safety Foundation (DB & Services) | Yes |
| 2 | [03-02](03-agent-dependability-safety/03-02-PLAN.md) | Integration & Triggers | Yes |
| 3 | [03-03](03-agent-dependability-safety/03-03-PLAN.md) | Evaluation & Resilience | Yes |

## Must-Haves
- **Truths**:
  - Tool calls are validated before execution.
  - Human handoff is triggered by explicit request or unsupported media.
  - Bot stops responding when session is paused.
  - AI failures result in friendly fallback messages.
  - Agent performance is measured against the baseline dataset.
- **Artifacts**:
  - `app/services/policy.py`
  - `app/services/handoff.py`
  - `scripts/eval_agent.py`
  - Migration file for `paused` column.
  - Updated `app/services/processor.py`.

## Requirements Covered
- REQ-prod-policy-gate
- REQ-prod-handoff
- REQ-prod-eval-gate
- REQ-bot-ai-fallback
- REQ-ai-no-hallucination
- REQ-ai-tools
- REQ-bot-aunt-notification
- REQ-sched-followup
- REQ-sched-retry-queue
