# Research — provenance note

These research files were **harvested from a parallel GSD spike** that ran in a separate clone
(`…/OneDrive/Desktop/.../ALYASMEEN_fixed/auntops_fixed`) using a different runtime ("Gemini"
session) on 2026-06-14. That spike ran the 4-agent project research we deliberately skipped in our
own `/gsd-new-project`, so the analysis is worth keeping — but it is **reference, not gospel**:
verify any claim against the live codebase before acting (same rule as the `ALYASMEEN/` wiki).

| File | Source |
|------|--------|
| `STACK.md`, `FEATURES.md`, `ARCHITECTURE.md`, `PITFALLS.md` | 4-agent project research (committed in the spike) |
| `RESEARCH-1.md`, `RESEARCH-2.md`, `RESEARCH-3.md` | Phase-level research drafts from the spike |
| `REF-BACKUP_DRILL.md` | The spike's backup/restore drill doc — directly relevant to M1 Phase 5 (BAK-01/02) |

**Not present:** `SUMMARY.md` — the spike paused before synthesis (per its `HANDOFF.json`).

**What we adopted from the spike (decisions, see PROJECT.md):** web+worker two-process
architecture with a durable inbox/outbox + idempotency (→ M2); structured logging (→ M2); agent
policy-gate + human-handoff + hybrid autonomy (→ M3); 12-month retention-then-anonymize; staged
pilot before launch.

**What we rejected from the spike's uncommitted code:** the Claude model downgrade
(`claude-3-haiku-20240307`), em-dash/encoding corruption, and the `DATABASE_URL` + SQLAlchemy
direct-Postgres job store (violates the HTTPS-RPC-only rule — our jobs are code-defined and need no
persistent job store). We rebuild the good patterns ourselves, deliberately, in the right phase.
