## Conflict Detection Report

> RESOLUTION (2026-06-14, user-approved): Both WARNINGS resolved toward the
> recommended prompt-engineering variants (SPEC-backed). PRD.md AI-05 superseded
> by PRD_PE CAT-01/03/04 (full catalog in system prompt). PRD.md AI-09 superseded
> by PRD_PE TOK-01 (600/400 token split). Roadmap routing proceeded after sign-off.

Mode: merge. Precedence: ADR > SPEC > PRD > DOC. No ADR-typed docs and no `locked: true` flags in the ingest set, so no LOCKED-vs-LOCKED checks fired. Existing context (`.planning/codebase/*.md`) contains no locked-decision blocks, so no merge BLOCKER fired. Cross-ref graph (PLAN_PE → PRD_PE → TODO_PE) is acyclic.

### BLOCKERS (0)

None.

### WARNINGS (2)

[WARNING] Competing acceptance variants for AI catalog grounding
  Found: docs/PRD.md AI-05 requires "product context (up to 6 matching products) injected inline in the user message"; docs/PRD_PROMPT_ENGINEERING.md CAT-01/CAT-03/CAT-04 require "all active products always injected into the system prompt as a <catalog> XML block, per-message _product_context removed"
  Impact: Two PRDs of equal precedence give divergent acceptance criteria for the same scope (AI product grounding); synthesis cannot pick without losing intent
  → Adopt one variant. Note: docs/PLAN_PROMPT_ENGINEERING.md (SPEC, higher precedence, ADR-PE-001) and the later date (2026-04-05, Status: Implemented) both adopt the full-catalog-in-system-prompt variant — recommended winner. Mark PRD.md AI-05 superseded to clear this warning.

[WARNING] Competing acceptance variants for AI max_tokens budget
  Found: docs/PRD.md AI-09 requires "max_tokens=400" uniformly; docs/PRD_PROMPT_ENGINEERING.md TOK-01 requires "max_tokens=600 when tools enabled, 400 when not"
  Impact: Two PRDs of equal precedence disagree on the token-budget acceptance criterion for the same scope; synthesis cannot pick without losing intent
  → Adopt one variant. Note: docs/PLAN_PROMPT_ENGINEERING.md (SPEC) Phase 5 and the later PRD adopt the 600/400 split — recommended winner. Mark PRD.md AI-09 superseded to clear this warning.

### INFO (4)

[INFO] Auto-resolved: SPEC > PRD on catalog injection
  Note: docs/PLAN_PROMPT_ENGINEERING.md (SPEC, ADR-PE-001) overrides docs/PRD.md AI-05 — full catalog injected in the system prompt wins over per-message inline injection. Recorded in decisions.md (ADR-PE-001) and requirements.md. The PRD-vs-PRD divergence is still surfaced as a WARNING above for explicit user sign-off.

[INFO] Auto-resolved: SPEC/PRD > DOC on prompt design described in PROMPTS.md
  Note: docs/PROMPTS.md (DOC) Principle 1 ("catalog context in the user message, not the system prompt") and Principle 4 ("max_tokens=400 for all calls") describe the superseded design. Higher-precedence docs/PLAN_PROMPT_ENGINEERING.md (SPEC) and docs/PRD_PROMPT_ENGINEERING.md (PRD) win — synthesized intel reflects system-prompt catalog injection and the 600/400 token split. PROMPTS.md retained in context.md as historical log with a superseded note.

[INFO] Auto-resolved: SPEC/PRD > DOC on knowledge-base architecture in TODO.md
  Note: docs/TODO.md (DOC) suggests knowledge files store_info.md/faq.md/return_policy.md/ingredients.md "loaded once at startup and all appended." Higher-precedence docs/PRD_PROMPT_ENGINEERING.md KB-01..KB-04 win — five specific files (store_info, shipping_policy, returns_policy, ingredients_faq, skin_advice) with trigger-based selective injection. Synthesized intel follows the PRD/SPEC version.

[INFO] Invoice mechanism discrepancy (PDF vs Wave) — RESOLVED 2026-06-14 (code-verified)
  Found: docs/PLAN.md (SPEC §3, §6) and docs/PRD.md (DASH-18) document only a PDF invoice generated and sent on status → done (app/services/pdf_invoice.py). docs/TODO.md (DOC) lists both "Wave invoicing wired (fires when status changes to done)" and "PDF invoice generated and sent" as completed.
  RESOLUTION: Invoicing is **PDF only**. Verified against live code: there is no wave_invoice.py — app/services/pdf_invoice.py:2 states it "replaces page_wave invoicing"; the invoice fires on status → done in app/routers/ui_api.py:147 via generate_invoice_pdf, sent as a WhatsApp document. The only remaining "Wave" tokens are a stale retry-queue action comment in app/db/schema.sql:90-93 (retry_actions.py actually handles the "pdf_invoice" action). The Wave references in docs/TODO.md and the project CLAUDE.md are stale and should not become a requirement. SPEC precedence and ground-truth code agree: PDF on done.
