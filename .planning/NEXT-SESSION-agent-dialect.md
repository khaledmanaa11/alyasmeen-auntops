# Next Session: Palestinian Dialect + Professional Selling Agent

> Paste the prompt below into a fresh Claude Code session in this repo.
> Written 2026-08-30, at the end of the live-rollout session that brought the bot online.

---

## The prompt (copy from here down)

The ALYASMEEN WhatsApp bot is LIVE in production (number +972 54-371-6513) and technically healthy — but its Arabic sounds generic and its selling behavior is amateur. This session's mission: make the bot speak **real Palestinian dialect** (اللهجة الفلسطينية — the way a warm shop owner in Ramallah actually talks, not MSA and not generic Levantine) and act like a **professional seller** (asks the right follow-up, recommends confidently, guides to checkout, never pushy, never invents facts).

**Orient first (do not skip):**
1. Read `.planning/STATE.md` — the "Last Action (2026-08-30)" entry explains exactly where the project stands.
2. Read `CLAUDE.md` (house rules: ONE AI file `app/services/ai_service.py`, one DB file, outbox-only sends, policy gate).
3. Read `ALYASMEEN/wiki/agent-safety.md` — the policy gate + five handoff triggers you must NOT weaken.
4. Read `docs/EVAL_GATE.md` — the mandatory release procedure for ANY agent-behavior change.
5. Read `app/services/ai_service.py` in full — the system prompt, the 5 tools, the escalation rules block.

**Hard constraints (all already enforced by tests/process — respect them):**
- The eval gate is BINDING: baseline is 85.1% overall (75.0% critical / 68.8% handoff / 100% informational) in `.planning/phases/03-agent-dependability-safety/03-EVAL-BASELINE.md`. After prompt changes, run the eval per `docs/EVAL_GATE.md` (`RUN_AGENT_EVAL=1`, costs real API money, sample first then `EVAL_SAMPLES=all`) and re-baseline HONESTLY per its procedure. A dialect change that drops tool-call accuracy is a regression, not a style win.
- Never let the model promise actions it has no tool for (no cancel/refund/edit-order promises) — the escalation rules in the system prompt exist for this.
- `tests/conftest.py` has `block_live_db` (live Supabase construction raises) — `.env` holds REAL production credentials; every new test mocks the seams. Full suite must stay green (483 passed baseline).
- All bot logic stays in `processor.py` / `ai_service.py` / `policy.py` / `handoff.py`.
- Local anthropic SDK is 0.84.0, pinned `<1.0` (1.x is breaking — migration is deliberately deferred; do not "upgrade while you're at it").

**Known quality material to build on:**
- The 11 analyzed eval failures in `03-EVAL-BASELINE.md` (e.g. post-checkout modification not handed off, clear_cart over-escalating, gift-packaging order missed) — fixing these IS part of "professional".
- `app/data/knowledge/` has 6 `.md` files feeding AI context — review/extend them (store info, shipping, returns, FAQ) so the bot answers like it owns the shop.
- `tests/data/whatsapp_agent_dataset.json` — 75 labeled messages; consider extending with dialect-expectation cases so the eval measures dialect quality too, not only tool behavior.
- The customer greeting already personalizes by name (from `customers` table) — extend that warmth, don't lose it.
- Khaled is a native speaker — use him as the judge for dialect authenticity (show him before/after reply pairs; his one-sentence verdict beats any automated metric).

**Suggested shape of the work** (adapt as needed): capture current behavior on 10–15 representative messages (transcripts via the FakeDB demo-script technique in the 2026-08-30 wiki log, or live tests from Khaled's phone) → rewrite the system prompt's voice section with an explicit Palestinian-dialect style guide + few-shot examples (خليها دافية وقصيرة، بالفلسطيني) → tighten selling behavior (one follow-up question max, recommend 1–2 products with prices, always name the next step) → knowledge-base pass → eval gate → Khaled's ear test → re-baseline per EVAL_GATE.md → update `ALYASMEEN/wiki/` + `.planning/STATE.md` so the next session inherits everything.

This can run as direct work (the eval gate is the safety net) or as a formal GSD phase via `/gsd-phase add` + `/gsd-discuss-phase` if it grows — your call after orienting.
