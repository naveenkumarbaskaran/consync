"""Logging configuration for consync.

Provides structured logging with:
- Console output (stderr) controlled by --verbose / --debug CLI flags
- File logging to .consync.log with rotation (default: 5MB × 3 backups)
- Audit log (.consync.audit.jsonl) — one JSON line per sync event with:
  timestamp, user, direction, source, target, constants (names + values)
- Per-module loggers following `consync.*` hierarchy

Usage in any module:
    import logging
    logger = logging.getLogger(__name__)
    logger.debug("Parsed %d constants from %s", count, filepath)
    logger.info("Synced source → target: %d constants", count)
    logger.warning("Both files changed — conflict detected")

CLI verbosity levels:
    (default)    WARNING+ to stderr, INFO+ to file
    --verbose    INFO+ to stderr, DEBUG+ to file
    --debug      DEBUG+ to stderr and file

Log file location: .consync.log in the working directory (or config dir).
Rotation: 5MB max, 3 backup files (.log.1, .log.2, .log.3).

Audit log: .consync.audit.jsonl — append-only, one JSON object per line.
Retention: configurable max_audit_lines (default 10000 lines ≈ 2-4MB).
"""

from __future__ import annotations

import getpass
import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from consync.models import Constant

# Package-level logger — all modules use children of this
ROOT_LOGGER_NAME = "consync"

# Defaults
DEFAULT_LOG_FILE = ".consync.log"
DEFAULT_AUDIT_FILE = ".consync.audit.jsonl"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
DEFAULT_BACKUP_COUNT = 3
DEFAULT_MAX_AUDIT_LINES = 10000
DEFAULT_FILE_LEVEL = logging.INFO
DEFAULT_CONSOLE_LEVEL = logging.WARNING

# Format strings
FILE_FORMAT = "%(asctime)s [%(levelname)-5s] %(name)s: %(message)s"
CONSOLE_FORMAT = "%(levelname)s: %(message)s"
DEBUG_FORMAT = "%(asctime)s.%(msecs)03d [%(levelname)-5s] %(name)s:%(funcName)s:%(lineno)d — %(message)s"


def setup_logging(
    *,
    verbose: bool = False,
    debug: bool = False,
    log_file: str | Path | None = DEFAULT_LOG_FILE,
    log_dir: Path | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    quiet: bool = False,
) -> logging.Logger:
    """Configure the consync logging hierarchy.

    Args:
        verbose: Show INFO+ on console (default: WARNING+).
        debug: Show DEBUG+ on console AND file.
        log_file: Log filename (None = disable file logging).
        log_dir: Directory for log file (default: cwd).
        max_bytes: Max log file size before rotation.
        backup_count: Number of rotated backup files to keep.
        quiet: Suppress all console output (file logging still active).

    Returns:
        The root 'consync' logger.
    """
    logger = logging.getLogger(ROOT_LOGGER_NAME)

    # Avoid duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)  # Capture everything; handlers filter

    # ─── Console handler (stderr) ───
    if not quiet:
        console = logging.StreamHandler()
        if debug:
            console.setLevel(logging.DEBUG)
            console.setFormatter(logging.Formatter(DEBUG_FORMAT, datefmt="%H:%M:%S"))
        elif verbose:
            console.setLevel(logging.INFO)
            console.setFormatter(logging.Formatter(CONSOLE_FORMAT))
        else:
            console.setLevel(logging.WARNING)
            console.setFormatter(logging.Formatter(CONSOLE_FORMAT))
        logger.addHandler(console)

    # ─── File handler (rotating) ───
    if log_file:
        log_path = (log_dir or Path.cwd()) / log_file
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_level = logging.DEBUG if debug else DEFAULT_FILE_LEVEL
            file_handler.setLevel(file_level)
            file_handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
            logger.addHandler(file_handler)
        except OSError:
            # Can't write log file (read-only FS, permissions) — silently skip
            pass

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a child logger under the consync namespace.

    Args:
        name: Typically __name__ (e.g., 'consync.sync', 'consync.parsers.csv_parser')

    Returns:
        Logger instance.
    """
    return logging.getLogger(name)


# ═══════════════════════════════════════════════════════════════════════════════
# Audit Log — structured JSON Lines file
# ═══════════════════════════════════════════════════════════════════════════════


def _get_user() -> str:
    """Get current OS username for audit trail."""
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def _serialize_value(value: Any) -> Any:
    """Serialize a constant value for JSON audit output."""
    if isinstance(value, list):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return value
    return str(value)


def write_audit_entry(
    *,
    direction: str,
    source: str,
    target: str,
    constants: list[Constant],
    result: str,
    dry_run: bool = False,
    audit_file: Path | None = None,
    max_lines: int = DEFAULT_MAX_AUDIT_LINES,
) -> None:
    """Append a structured audit entry to .consync.audit.jsonl.

    Each line is a self-contained JSON object:
    {
        "timestamp": "2026-05-05T08:45:12Z",
        "user": "naveenkumar",
        "direction": "source → target",
        "source": "params.csv",
        "target": "ecu_params.h",
        "result": "synced",
        "count": 5,
        "dry_run": false,
        "constants": [
            {"name": "BRAKE_MAX", "value": 250, "unit": "bar"},
            {"name": "THRESHOLDS", "value": [50, 100, 150]},
            ...
        ]
    }

    Retention: trims oldest lines when file exceeds max_lines.
    """
    if audit_file is None:
        audit_file = Path.cwd() / DEFAULT_AUDIT_FILE

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "user": _get_user(),
        "direction": direction,
        "source": source,
        "target": target,
        "result": result,
        "count": len(constants),
        "dry_run": dry_run,
        "constants": [
            {
                "name": c.name,
                "value": _serialize_value(c.value),
                **({"unit": c.unit} if c.unit else {}),
            }
            for c in constants
        ],
    }

    try:
        audit_file.parent.mkdir(parents=True, exist_ok=True)

        # Append entry
        with audit_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Retention: trim if over max_lines
        _trim_audit_file(audit_file, max_lines)

    except OSError:
        # Can't write audit — log warning but don't fail sync
        logger = logging.getLogger(ROOT_LOGGER_NAME)
        logger.warning("Could not write audit log to %s", audit_file)


def _trim_audit_file(audit_file: Path, max_lines: int) -> None:
    """Trim audit file to max_lines, keeping newest entries."""
    try:
        lines = audit_file.read_text(encoding="utf-8").splitlines()
        if len(lines) > max_lines:
            # Keep the last max_lines entries
            trimmed = lines[-max_lines:]
            audit_file.write_text("\n".join(trimmed) + "\n", encoding="utf-8")
    except OSError:
        pass


def read_audit_log(
    audit_file: Path | None = None,
    last_n: int = 20,
) -> list[dict]:
    """Read the last N entries from the audit log.

    Args:
        audit_file: Path to .consync.audit.jsonl (default: cwd).
        last_n: Number of recent entries to return.

    Returns:
        List of parsed audit entries (newest last).
    """
    if audit_file is None:
        audit_file = Path.cwd() / DEFAULT_AUDIT_FILE

    if not audit_file.exists():
        return []

    lines = audit_file.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines[-last_n:]:
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries
