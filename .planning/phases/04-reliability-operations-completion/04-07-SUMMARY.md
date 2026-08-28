---
phase: 04-reliability-operations-completion
plan: 07
subsystem: infra
tags: [supabase, railway, apscheduler, migrations, backup-restore, service_role, rls, nixpacks]

# Dependency graph
requires:
  - phase: 04-reliability-operations-completion
    provides: "04-01 (outbox) through 04-06 (alerts UI) — this plan gated on all six prior 04-0x plans being complete and the suite green before touching production credentials/grants"
provides:
  - "supabase/migrations/20260825000004_revert_anon_grants.sql — revokes run_query/run_exec from anon/authenticated again, applied live"
  - "Railway worker service (custom start command `python -m app.worker`) provisioned and running with DATABASE_URL-backed SQLAlchemyJobStore, proven persistent across a real restart against the live apscheduler_jobs table"
  - "SUPABASE_KEY = service_role live in Railway (web + worker) and local .env, verified end-to-end before the revert migration shipped"
  - "All 11 files in supabase/migrations/ applied to the live Supabase project (ppwcfmuetgczclmnzvqr) via `supabase db push --linked`, including repair of stale remote migration history and non-destructive resolution of dead-June-line schema drift"
  - "Real backup/restore drill executed (native pg_dump -> throwaway project -> psql restore), verification counts matched production exactly, recorded in docs/BACKUP_DRILL.md's Drill Log"
  - "railway.json pinning the Railway builder to Nixpacks, fixing a Railpack mise-attestation build failure that was blocking all deploys"
affects: ["Phase 5 (Operator Security & UX) and Phase 6 (Production Go-Live) — both now build on a live deployment actually running on service_role with a persistent worker scheduler and applied migrations, not just documented-as-pending"]

# Tech tracking
tech-stack:
  added: ["railway.json (Nixpacks builder pin)"]
  patterns:
    - "Railway Procfile `worker:` process types do not auto-provision a Railway service — a service with a custom start command must be created manually in the Railway dashboard"
    - "`supabase migration repair --status reverted` reconciles stale/renamed remote migration_history rows before `db push` will proceed"
    - "Non-destructive live schema-drift resolution: rename conflicting tables aside with a suffix (e.g. `_oldjune`) rather than dropping, preserving old data while letting new migrations create the correct shape"
    - "Backup/restore drills use native `pg_dump -n public --no-owner --no-privileges` (not `supabase db dump`, which requires Docker) per the corrected docs/BACKUP_DRILL.md"

key-files:
  created: [supabase/migrations/20260825000004_revert_anon_grants.sql, railway.json]
  modified: [CLAUDE.md, docs/BACKUP_DRILL.md, Procfile, .gitignore]

key-decisions:
  - "SUPABASE_KEY switched to service_role in Railway (both services) and local .env, and verified end-to-end (/health + a full order round-trip on both), BEFORE the anon-revoke migration was applied — the exact safe ordering the plan's Task 1 warning specified, avoiding the outage 20260825000001 was written to fix"
  - "Railway build pinned to Nixpacks via a new railway.json after Railway's default Railpack builder failed all builds on a mise python-attestation error unrelated to this repo's code"
  - "Procfile worker entry changed from `python app/worker.py` to `python -m app.worker` — the script-style invocation could not resolve `app.*` imports, which would have crashed the worker service on every boot"
  - "Live `webhook_events`/`outbox_jobs` tables left over from the retired June architecture line were renamed aside with an `_oldjune` suffix (not dropped) so `db push` could create the correct current-architecture tables without destroying the 8 stale historical rows"
  - "Backup/restore drill followed the corrected BACKUP_DRILL.md path: native `pg_dump -n public` (Docker not available for `supabase db dump`) into a throwaway free-tier Supabase project, restored via `psql`, then deleted"

patterns-established:
  - "Live production credential/grant changes for this project always go: switch credential -> verify end-to-end -> only then apply the migration that revokes the old credential's access (never revoke-then-switch)"

# Metrics
duration: ~1h51m (2026-08-28T12:28:59Z-14:19:31Z, Task 1 commit through the final drill-log commit; spans automated Task 1 plus three live operator checkpoints)
completed: 2026-08-28
---

# Phase 4 Plan 07: Live Rollout Checkpoint Summary

**Live production cutover completing Phase 4: Supabase credential switched to `service_role` end-to-end, a Railway worker service provisioned with a `DATABASE_URL`-backed job store proven to survive a real restart, all 11 migrations applied to the live project (including repair of stale migration history and non-destructive resolution of dead-architecture schema drift), and a real backup/restore drill executed with matching verification counts.**

## Performance

- **Duration:** ~1h51m (Task 1 automated write, then three human-action checkpoints performed live by the operator with orchestrator guidance)
- **Started:** 2026-08-28T12:28:59Z (Task 1 commit `d7bc7e0`)
- **Completed:** 2026-08-28T14:19:31Z (Drill Log commit `780649e`)
- **Tasks:** 4 (1 automated + 3 checkpoint:human-action, all complete)
- **Files modified:** 6 relevant to this plan (2 created, 4 modified) across 5 commits, plus live-only changes (Railway service config, Supabase credentials/grants/schema) that have no corresponding repo diff

## Accomplishments
- Revert-anon-grants migration written with an explicit ordering warning, then correctly applied live only after the service_role switch was verified — closing the loop 20260825000001 opened.
- A Railway **worker** service now exists (it did not before — Procfile process types don't auto-create Railway services) and its APScheduler job store is proven persistent: `next_run_time` for `monthly_report` was identical before and after a real operator-initiated worker restart, checked directly against the live `apscheduler_jobs` table.
- The deployed app (Railway web + worker) and local dev both run on `SUPABASE_KEY=service_role`, verified via `/health` and a full order round-trip on both, before the anon-revoke migration shipped.
- `anon`/`authenticated` can no longer execute `run_query`/`run_exec` — confirmed working because all RPC traffic (local seam calls + worker polling loops, HTTP 200) continued unaffected after the revoke, since the app now authenticates as `service_role`.
- All 11 files under `supabase/migrations/` are applied to the live Supabase project (`ppwcfmuetgczclmnzvqr`), after repairing 5 stale remote migration-history rows and non-destructively resolving schema drift from an old, superseded architecture line.
- A real backup/restore drill ran end-to-end: native `pg_dump` of the live public schema, restored via `psql` into a throwaway free-tier project, verification counts matched production exactly (products=3, orders=8, order_lines=16, customers=22, chat_history=54); the throwaway project was deleted afterward and a truthful row was added to `docs/BACKUP_DRILL.md`'s Drill Log.
- Two blockers found and fixed en route to Task 2 that would otherwise have silently broken the worker in production: a Procfile invocation bug (`python app/worker.py` -> `python -m app.worker`) and a Railway builder failure (Railpack mise-attestation error) resolved by pinning to Nixpacks via a new `railway.json`.

## Task Commits

Each task was committed atomically (Tasks 2-4 are `checkpoint:human-action` — performed live against Railway/Supabase dashboards by the operator; no code changes for Tasks 2-3, deviations found during Task 2 and Task 4 were committed):

1. **Task 1: Revert migration + rollout docs** - `d7bc7e0` (docs) — prior agent, this session verified it
2. **Task 2 deviation: Procfile worker entry fix** - `2f8908f` (fix)
3. **Task 2 deviation: pin Railway builder to Nixpacks** - `0f9af1c` (fix)
4. **Task 3: service_role switch** - no code commit (Railway/local .env credential change only, verified live)
5. **Task 4 deviation: correct backup drill for no-Docker `pg_dump`** - `8a4f72e` (docs)
6. **Task 4 deviation: gitignore backup dumps, note `-n public` requirement** - `f8d4bf7` (docs)
7. **Task 4: record passing drill in Drill Log** - `780649e` (docs)

**Plan metadata:** _this commit_ (docs: complete live rollout checkpoint plan)

## Files Created/Modified
- `supabase/migrations/20260825000004_revert_anon_grants.sql` - Revokes `run_query`/`run_exec` EXECUTE from `anon, authenticated`; applied live in Task 4.
- `railway.json` - Pins the Railway build to the Nixpacks builder, fixing a Railpack mise-attestation error that blocked all worker-service deploys.
- `Procfile` - `worker:` entry corrected from `python app/worker.py` to `python -m app.worker` so `app.*` imports resolve.
- `CLAUDE.md` - Documents `SUPABASE_KEY` as the `service_role` key (server-side only) and its security implications.
- `docs/BACKUP_DRILL.md` - Corrected to the verified no-Docker CLI sequence (native `pg_dump`, not `supabase db dump`); new Drill Log row recorded.
- `.gitignore` - Added `backup_*.sql` so dump files taken during the drill are never committed.

**Live-only changes with no repo diff** (Railway dashboards + Supabase project `ppwcfmuetgczclmnzvqr`):
- New Railway worker service created with custom start command, `DATABASE_URL` (Session Pooler) set.
- `SUPABASE_KEY` set to `service_role` on both Railway services and local `.env`.
- `supabase migration repair --status reverted` applied to 5 stale remote migration-history rows.
- Live `webhook_events`/`outbox_jobs` tables (and their 6 indexes) from the retired June architecture renamed aside with an `_oldjune` suffix, preserving 8 stale rows, non-destructively.
- `supabase db push --linked` applied all 11 migrations.
- Throwaway restore-target Supabase project created, verified, and deleted.

## Decisions Made
- **Ordering enforced exactly as specified**: service_role switch verified end-to-end on both Railway and local *before* the anon-revoke migration was applied, avoiding the exact outage class `20260825000001` was written to fix.
- **Nixpacks over Railpack**: Railway's default Railpack builder failed all builds (unrelated mise python-attestation error); pinned to Nixpacks via `railway.json` rather than debugging Railpack further, since Nixpacks was already the project's working builder historically.
- **Rename, don't drop, drifted live tables**: the old `webhook_events`/`outbox_jobs` from the dead June architecture line were renamed aside (`_oldjune` suffix) instead of dropped, preserving the 8 stale rows for the operator to review/drop later once confident, while letting `db push` create the current-architecture tables cleanly.
- **Native `pg_dump` over `supabase db dump`**: the CLI's own dump command requires Docker Desktop (not installed); the drill instead used `pg_dump -n public --no-owner --no-privileges` against the Session Pooler connection string, which needs no Docker and produces an equivalent restorable dump.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Procfile worker entry could not resolve `app.*` imports**
- **Found during:** Task 2 (creating the Railway worker service)
- **Issue:** `worker: python app/worker.py` runs the file as a top-level script, which cannot resolve the package-relative `app.*` imports `app/worker.py` uses — the worker would crash on every boot once a Railway worker service actually existed to run it.
- **Fix:** Changed to `worker: python -m app.worker`, which runs the module with the package root on `sys.path`.
- **Files modified:** `Procfile`
- **Verification:** Worker service deployed and boot logs confirmed the process starts and registers scheduler jobs.
- **Committed in:** `2f8908f`

**2. [Rule 3 - Blocking] Railway's default builder failed all builds**
- **Found during:** Task 2 (first deploy of the new worker service)
- **Issue:** Railway's Railpack builder failed with a mise python-attestation error, unrelated to this repo's code, blocking every deploy attempt for the new service.
- **Fix:** Added `railway.json` pinning `"builder": "NIXPACKS"`.
- **Files modified:** `railway.json` (new)
- **Verification:** Subsequent deploy succeeded on Nixpacks.
- **Committed in:** `0f9af1c`

**3. [Rule 3 - Blocking] `supabase db push` blocked by stale remote migration history**
- **Found during:** Task 4 (first `db push --linked` attempt)
- **Issue:** 5 remote `migration_history` rows (`20260315171900`, `20260315172524`, `20260316170505`, `20260405113545`, `20260615220700`) referenced migration files from the pre-rewrite/dead-June era no longer present in the repo, blocking `db push`.
- **Fix:** `supabase migration repair --status reverted` on each stale version.
- **Files modified:** none (remote migration_history table only, no repo diff)
- **Verification:** `db push` proceeded past the history check on retry.
- **Committed in:** n/a (live-only operation)

**4. [Rule 1 - Bug] Live schema drift from the retired June architecture line blocked migrations**
- **Found during:** Task 4 (`db push` after the history repair)
- **Issue:** The live `webhook_events` table still had the old June-architecture shape (`wamid`/`status` columns, no `processed`) and `outbox_jobs` had `transport`/`recipient` columns with 8 stale rows — incompatible with the current migrations' expected shape, causing `db push` to fail on schema conflicts.
- **Fix:** Renamed both tables and their 6 indexes aside with an `_oldjune` suffix (non-destructive — old data preserved), then re-ran `db push`, which created the correct current-architecture tables.
- **Files modified:** none (live schema only, no repo diff)
- **Verification:** Second `db push` applied all remaining migrations cleanly; post-verification confirmed `webhook_events` has `phone`/`processed`/`wamid`/`attempts` and `outbox_jobs` has `kind`/`phone`/`last_error`/`updated_at`; `audit_logs` + `handoffs` created; 11 RLS policies present.
- **Committed in:** n/a (live-only operation)

**5. [Rule 1 - Bug] `docs/BACKUP_DRILL.md` incorrectly assumed `supabase db dump` needed no Docker**
- **Found during:** Task 4 (attempting the drill per the Task 1 doc rewrite)
- **Issue:** `supabase db dump --linked` failed with "Docker Desktop is a prerequisite" — Docker is not installed in this environment, and the doc (written in Task 1, before this was tested live) claimed the full drill sequence was Docker-free.
- **Fix:** Corrected the doc to use native `pg_dump -n public --no-owner --no-privileges` instead (from the official PostgreSQL Windows installer), which needs no Docker; documented that `-n public` is required to avoid pulling in Supabase's internal `auth`/`storage` schemas.
- **Files modified:** `docs/BACKUP_DRILL.md`, `.gitignore` (added `backup_*.sql`)
- **Verification:** `pg_dump` ran successfully and produced a restorable dump; restore drill (below) succeeded using it.
- **Committed in:** `8a4f72e`, `f8d4bf7`

---

**Total deviations:** 5 (4 auto-fixed as blocking/bug per Rules 1/3, all necessary to reach a working live deployment; 2 of the 5 are live-only operations with no repo diff to commit). One additional cosmetic gap noted below, not fixed.
**Impact on plan:** All fixes were required for the deployment to function or for the drill/migration steps to actually succeed — no scope creep. The `_oldjune` rename is reversible (old data preserved) and left for the operator to drop once confident, rather than deleted unilaterally.

## Issues Encountered
- **Cosmetic, deferred:** worker `structlog` lines (e.g. "Using SQLAlchemyJobStore") are not visible in Railway's log viewer, though APScheduler's own stdlib logging output is. Persistence itself was still independently verified via the live `apscheduler_jobs` table (`next_run_time` unchanged across a real restart), so this does not block the success criterion — only the specified "check worker logs for this line" verification step was inconclusive. A structlog-handler/Railway-logging configuration fix is deferred as out of scope for this plan.
- **Residual, deferred:** `webhook_events_oldjune` / `outbox_jobs_oldjune` (8 stale rows) exist only as a live rename with no corresponding migration file — the drift resolution was necessarily live-only (repo migrations describe the target/current schema, not one-off remediation of a since-superseded live database state). Recommend the operator drop these tables directly once confident the old data isn't needed, or a future light migration can formalize the drop.

## User Setup Required

None remaining — all `user_setup` items from this plan's frontmatter (`SUPABASE_KEY` on Supabase+Railway, Railway `DATABASE_URL`, `supabase link` DB password) were completed live by the operator during Tasks 2-4, as recorded above.

## Next Phase Readiness
- **Phase 4 is complete: 7/7 plans done.** All 5 Phase 4 success criteria are now genuinely true in production, not just documented-as-pending:
  1. `retry_queue.py`/`gatekeeper.py` resolved (04-02, 04-04).
  2. All migrations applied live; app verified end-to-end on the key it actually ships with (`service_role`) — this plan.
  3. Worker job store persistent in production, proven across a real restart — this plan.
  4. Dead-letter dashboard with one-click retry (04-05, 04-06).
  5. Real backup/restore drill executed and recorded — this plan.
- Production state: Railway web + worker services both green, worker polling loops verified live against the migrated schema. `origin/main` (PRs #5, #6 merged) has all of this through commit `0f9af1c`; this plan's final two documentation commits (`f8d4bf7`, `780649e`) remain on `fix/production-hardening` pending a future merge.
- Two deferred, non-blocking items carried forward (see Issues Encountered above): structlog visibility in Railway logs, and formalizing the `_oldjune` table drop.
- Ready for Phase 3 (Agent Dependability & Safety) execution/re-verification, and Phase 5 (Operator Security & UX) planning — both were blocked on this plan's live-credential and migration-rollout work being real, not assumed.

---
*Phase: 04-reliability-operations-completion*
*Completed: 2026-08-28*

## Self-Check: PASSED

- FOUND: supabase/migrations/20260825000004_revert_anon_grants.sql
- FOUND: railway.json
- FOUND: docs/BACKUP_DRILL.md (Drill Log row for 2026-08-28 confirmed present)
- FOUND commit: d7bc7e0
- FOUND commit: 2f8908f
- FOUND commit: 0f9af1c
- FOUND commit: 8a4f72e
- FOUND commit: f8d4bf7
- FOUND commit: 780649e
