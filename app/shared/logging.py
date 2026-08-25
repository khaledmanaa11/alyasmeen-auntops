import logging
import os
import sys

import structlog

def setup_logging():
    """Configure structlog for JSON logging in production and colored console in dev."""
    
    # Check if we're in production based on ENVIRONMENT env var
    # Default to production (JSON) for safety unless explicitly set to development
    is_production = os.getenv("ENVIRONMENT", "production").lower() == "production"

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if is_production:
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Standard logging integration
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )
