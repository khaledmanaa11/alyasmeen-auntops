"""
test_scheduler_persistence.py — Proof that SQLAlchemyJobStore persistence
survives a worker restart.

`app/worker.py` wires `SQLAlchemyJobStore(url=Config.DATABASE_URL)` when
DATABASE_URL is set (falling back to an in-memory job store otherwise, which
loses all scheduling state on every restart — see Config.DATABASE_URL usage
in app/worker.py). This test verifies that mechanism genuinely persists job
scheduling state (next_run_time) across independent scheduler instances —
i.e. across what a worker process restart looks like — using a local sqlite
file as the backing store. This is the exact same SQLAlchemy jobstore code
path Postgres would use; only the connection string differs, so no live
Supabase/Railway credentials are needed here.

The live production check — DATABASE_URL actually set on Railway with the
Supabase Session Pooler connection string — is a separate operator
checkpoint. See plan 04-07.
"""
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler


def _noop_job():
    """Module-level (picklable) stand-in for a real scheduled job, e.g.
    app/services/monthly_report.py's send_monthly_report. SQLAlchemyJobStore
    persists jobs by pickling a textual module:function reference to disk —
    a lambda or closure has no such reference and cannot be serialized, so a
    module-level function is required here (and in any real job app/worker.py
    schedules)."""


def test_job_next_run_time_survives_scheduler_restart(tmp_path):
    """A job's next_run_time, once persisted, is read back identically by a
    brand-new scheduler instance pointed at the same on-disk store — proving
    the scheduling state outlives the process that created it."""
    db_url = f"sqlite:///{tmp_path / 'jobstore.db'}"

    # Scheduler A: mirrors app/worker.py's real monthly_report job shape.
    scheduler_a = BackgroundScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=db_url)}
    )
    scheduler_a.start()
    scheduler_a.add_job(
        _noop_job,
        "cron",
        day=1,
        hour=8,
        minute=0,
        id="monthly_report",
        replace_existing=True,
    )

    job_a = scheduler_a.get_job("monthly_report")
    assert job_a is not None
    next_run_time_a = job_a.next_run_time
    assert next_run_time_a is not None

    # Simulates the worker process ending.
    scheduler_a.shutdown(wait=False)

    # Scheduler B: a brand-new instance pointed at the SAME db_url — this is
    # the "restart": a new process would re-read the same on-disk store.
    scheduler_b = BackgroundScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=db_url)}
    )
    scheduler_b.start()
    try:
        job_b = scheduler_b.get_job("monthly_report")
        assert job_b is not None
        assert job_b.next_run_time == next_run_time_a
    finally:
        scheduler_b.shutdown(wait=False)


def test_job_store_is_isolated_per_database(tmp_path):
    """Control case guarding against a false positive from in-process
    caching: a scheduler pointed at a DIFFERENT, freshly-created empty
    sqlite file must NOT see the job persisted in test 1's database — proving
    persistence genuinely comes from the shared on-disk store, not some
    other in-memory cache."""
    db_url = f"sqlite:///{tmp_path / 'jobstore_a.db'}"
    other_db_url = f"sqlite:///{tmp_path / 'jobstore_c.db'}"

    scheduler_a = BackgroundScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=db_url)}
    )
    scheduler_a.start()
    scheduler_a.add_job(
        _noop_job,
        "cron",
        day=1,
        hour=8,
        minute=0,
        id="monthly_report",
        replace_existing=True,
    )
    assert scheduler_a.get_job("monthly_report") is not None
    scheduler_a.shutdown(wait=False)

    scheduler_c = BackgroundScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=other_db_url)}
    )
    scheduler_c.start()
    try:
        assert scheduler_c.get_job("monthly_report") is None
    finally:
        scheduler_c.shutdown(wait=False)
