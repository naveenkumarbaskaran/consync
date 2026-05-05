"""Backup & Recovery — snapshot files before write, restore on demand.

Before every sync that writes a file, consync saves the previous version to
.consync/backups/<filename>.<timestamp>.bak

Recovery options:
    consync recover                    # List available snapshots
    consync recover --file out.h       # List snapshots for a specific file
    consync recover --file out.h --at 2026-05-05T08:45:12  # Restore exact timestamp
    consync recover --file out.h --last  # Restore most recent backup

Retention: keeps last 20 backups per file (configurable). Oldest auto-deleted.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = ".consync/backups"
DEFAULT_MAX_BACKUPS_PER_FILE = 20


def backup_file(
    filepath: Path,
    backup_dir: Path | None = None,
    max_backups: int = DEFAULT_MAX_BACKUPS_PER_FILE,
) -> Path | None:
    """Create a timestamped backup of a file before overwriting.

    Args:
        filepath: The file to back up.
        backup_dir: Where to store backups (default: .consync/backups/).
        max_backups: Max backups to keep per file (oldest trimmed).

    Returns:
        Path to the backup file, or None if file doesn't exist (nothing to back up).
    """
    if not filepath.exists():
        return None

    if backup_dir is None:
        backup_dir = filepath.parent / DEFAULT_BACKUP_DIR

    backup_dir.mkdir(parents=True, exist_ok=True)

    # Timestamp format: YYYYMMDD_HHMMSS (sortable, filesystem-safe)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"{filepath.name}.{ts}.bak"
    backup_path = backup_dir / backup_name

    shutil.copy2(filepath, backup_path)
    logger.debug("Backed up %s → %s", filepath.name, backup_path)

    # Trim old backups
    _trim_backups(backup_dir, filepath.name, max_backups)

    return backup_path


def _trim_backups(backup_dir: Path, filename: str, max_backups: int) -> None:
    """Keep only the most recent N backups for a given filename."""
    pattern = f"{filename}.*.bak"
    backups = sorted(backup_dir.glob(pattern))  # sorted by timestamp in name

    if len(backups) > max_backups:
        for old in backups[:-max_backups]:
            old.unlink(missing_ok=True)
            logger.debug("Trimmed old backup: %s", old.name)


def list_backups(
    filepath: Path | None = None,
    backup_dir: Path | None = None,
    project_dir: Path | None = None,
) -> list[dict]:
    """List available backup snapshots.

    Args:
        filepath: Filter to backups of this specific file (optional).
        backup_dir: Backup directory (default: .consync/backups/ in project_dir).
        project_dir: Project root (default: cwd).

    Returns:
        List of dicts: {"file": str, "timestamp": str, "path": Path, "size": int}
    """
    if project_dir is None:
        project_dir = Path.cwd()
    if backup_dir is None:
        backup_dir = project_dir / DEFAULT_BACKUP_DIR

    if not backup_dir.exists():
        return []

    results = []
    pattern = f"{filepath.name}.*.bak" if filepath else "*.bak"

    for bak in sorted(backup_dir.glob(pattern)):
        parts = bak.name.rsplit(".", 2)  # name.TIMESTAMP.bak
        if len(parts) >= 3:
            original_name = parts[0]
            ts_str = parts[1]
            # Parse timestamp back to ISO format
            try:
                ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
                iso_ts = ts.isoformat(timespec="seconds")
            except ValueError:
                iso_ts = ts_str

            results.append({
                "file": original_name,
                "timestamp": iso_ts,
                "ts_raw": ts_str,
                "path": bak,
                "size": bak.stat().st_size,
            })

    return results


def recover_file(
    filepath: Path,
    timestamp: str | None = None,
    last: bool = False,
    backup_dir: Path | None = None,
    project_dir: Path | None = None,
) -> Path | None:
    """Restore a file from a backup snapshot.

    Args:
        filepath: The file to restore.
        timestamp: ISO timestamp to restore to (e.g., "2026-05-05T08:45:12").
        last: If True, restore the most recent backup.
        backup_dir: Backup directory.
        project_dir: Project root.

    Returns:
        Path to the restored file, or None if no matching backup found.
    """
    backups = list_backups(
        filepath=filepath, backup_dir=backup_dir, project_dir=project_dir
    )

    if not backups:
        logger.warning("No backups found for %s", filepath.name)
        return None

    if last:
        chosen = backups[-1]  # most recent
    elif timestamp:
        # Match by timestamp prefix (ISO or raw format)
        ts_normalized = timestamp.replace("T", "").replace("-", "").replace(":", "")[:15]
        chosen = None
        for b in backups:
            if b["ts_raw"].startswith(ts_normalized[:8]):
                # Date match — find closest
                if ts_normalized in b["ts_raw"].replace("_", ""):
                    chosen = b
                    break
        if chosen is None:
            # Fallback: find nearest timestamp
            chosen = backups[-1]
            logger.warning(
                "Exact timestamp %s not found, using nearest: %s",
                timestamp, chosen["timestamp"],
            )
    else:
        # No timestamp specified — use most recent
        chosen = backups[-1]

    # Back up current file before restoring (safety net)
    if filepath.exists():
        safety_dir = (project_dir or Path.cwd()) / ".consync/backups"
        safety_dir.mkdir(parents=True, exist_ok=True)
        safety_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safety_path = safety_dir / f"{filepath.name}.{safety_ts}_pre_recover.bak"
        shutil.copy2(filepath, safety_path)
        logger.info("Safety backup of current state: %s", safety_path.name)

    # Restore
    shutil.copy2(chosen["path"], filepath)
    logger.info("Restored %s to %s", filepath.name, chosen["timestamp"])

    return filepath
