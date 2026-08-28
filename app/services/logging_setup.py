"""
Logging setup (Phase 8, SOURCE_OF_TRUTH Section 14).

Gives the service a real log file (logs/service.log, rotated at ~1 MB so it
can't grow forever) plus console output. When something breaks, Section 14's
first move is "check logs/" — this is what makes that possible.

RotatingFileHandler: after service.log reaches maxBytes it's renamed to
service.log.1 and a fresh file starts; backupCount caps how many old files
are kept. Simple disk hygiene without a log-management system.
"""

import logging
from logging.handlers import RotatingFileHandler

from app.config import BASE_DIR

LOG_DIR = BASE_DIR / "logs"


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        LOG_DIR / "service.log",
        maxBytes=1_000_000,  # ~1 MB per file
        backupCount=2,       # keep service.log.1 and service.log.2
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[file_handler, logging.StreamHandler()],
    )

    # Uvicorn configures its own loggers and stops them from propagating to
    # the root logger, so without this our log file would stay empty even
    # though requests were being served. Attach the file handler to
    # uvicorn's loggers explicitly (console output stays uvicorn's own).
    for name in ("uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.append(file_handler)
        uvicorn_logger.propagate = False  # avoid writing the same line twice
