"""
backup.py — Automated nightly export of Supabase database.

Runs nightly via APScheduler (wired in main.py).
Uses 'npx supabase db dump' to create a data-only SQL export
and saves it to the local backups/ directory.
"""
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path

from app.services.config import Config

log = logging.getLogger(__name__)


def run_backup() -> None:
    """Run an automated export of the Supabase database data."""
    if not Config.SUPABASE_DB_PASSWORD:
        log.warning("backup: SUPABASE_DB_PASSWORD not set — skipping nightly export")
        return

    # 1. Ensure backups directory exists
    project_root = Path(__file__).resolve().parents[2]
    backup_dir = project_root / "backups"
    try:
        backup_dir.mkdir(exist_ok=True)
    except Exception:
        log.exception("backup: failed to create backups directory")
        return

    # 2. Construct filename
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = f"backup_{timestamp}.sql"
    filepath = backup_dir / filename

    # 3. Run supabase db dump
    # We use --data-only for M1 backup insurance; schema is already versioned in migrations.
    # --linked tells the CLI to use the project linked to this directory.
    cmd = [
        "npx", "supabase", "db", "dump",
        "--linked",
        "--data-only",
        "--output", str(filepath)
    ]

    # Set the DB password in environment so the CLI can run unattended
    env = os.environ.copy()
    env["SUPABASE_DB_PASSWORD"] = Config.SUPABASE_DB_PASSWORD

    log.info("backup: starting data-only export to %s", filename)
    try:
        # Use shell=True for npx compatibility on Windows
        subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            check=True,
            shell=True
        )
        log.info("backup: export completed successfully: %s", filename)
    except subprocess.CalledProcessError as e:
        log.error("backup: export failed (exit %d): %s", e.returncode, e.stderr)
        # Attempt to remove partial file if it exists
        if filepath.exists():
            filepath.unlink()
        return
    except Exception:
        log.exception("backup: unexpected error during export")
        return

    # 4. Retention (keep last 7 days of backups)
    try:
        _prune_backups(backup_dir)
    except Exception:
        log.exception("backup: failed to prune old backups")


def _prune_backups(backup_dir: Path) -> None:
    """Keep only the 7 most recent backup files to bound growth."""
    backups = sorted(
        backup_dir.glob("backup_*.sql"),
        key=os.path.getmtime,
        reverse=True
    )
    if len(backups) > 7:
        for old_backup in backups[7:]:
            try:
                old_backup.unlink()
                log.info("backup: pruned old file %s", old_backup.name)
            except Exception:
                log.warning("backup: could not delete old file %s", old_backup.name)


if __name__ == "__main__":
    # Allow manual test run: python -m app.services.backup
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    run_backup()
