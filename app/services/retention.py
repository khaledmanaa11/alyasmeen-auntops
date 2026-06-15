"""
retention.py — Automated retention jobs for unbounded tables.

Runs daily via APScheduler (wired in main.py).
Prunes old chat history (RET-01) and resolved retry queue rows (RET-02)
based on windows configured in config/setup.json.
"""
import logging

from app.db.database import execute
from app.services.config import Config

log = logging.getLogger(__name__)


def run_retention() -> None:
    """Run pruning jobs for chat_history and retry_queue."""
    retention_cfg = Config.APP_CONFIG.get("retention", {})
    
    # 1. Prune chat_history (RET-01)
    # Default to 30 days if not configured
    chat_days = retention_cfg.get("chat_history_days", 30)
    try:
        execute(
            "DELETE FROM chat_history WHERE created_at < now() - (%s * INTERVAL '1 day')",
            (chat_days,)
        )
        log.info("retention: pruned chat_history older than %d days", chat_days)
    except Exception:
        log.exception("retention: failed to prune chat_history")

    # 2. Prune retry_queue (RET-02)
    # Only prune RESOLVED rows. Default to 30 days if not configured.
    retry_days = retention_cfg.get("retry_queue_days", 30)
    try:
        execute(
            "DELETE FROM retry_queue WHERE resolved = TRUE AND created_at < now() - (%s * INTERVAL '1 day')",
            (retry_days,)
        )
        log.info("retention: pruned resolved retry_queue older than %d days", retry_days)
    except Exception:
        log.exception("retention: failed to prune retry_queue")


if __name__ == "__main__":
    # Allow manual test run: python -m app.services.retention
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    run_retention()
