"""File watcher — auto-syncs when source or target files change.

Uses the `watchdog` library for cross-platform file system monitoring.
No `brew install` required — pure Python.

Event handling:
  - Changes during debounce are QUEUED, not dropped
  - After debounce expires, all queued events are coalesced into one sync
  - Lock conflicts trigger automatic retry after a short delay
  - Errors are logged but the watcher continues (resilient)
  - On startup, a full sync is run to recover from any drift
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import click

from consync.config import load_config
from consync.sync import sync, SyncResult

logger = logging.getLogger(__name__)

# Max retries when lock is held by another process
LOCK_RETRY_ATTEMPTS = 3
LOCK_RETRY_DELAY = 2.0  # seconds between retries


def start_watcher(
    config_path: str | Path | None = None,
    debounce_override: float | None = None,
):
    """Start watching all mapped files and auto-sync on changes.

    Blocks until KeyboardInterrupt.

    Behaviour:
      - Runs a full sync on startup to catch any drift
      - Queues events during debounce (never drops changes)
      - Retries on lock conflict (up to 3 times)
      - Continues watching after errors (resilient)
    """
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    cfg = load_config(config_path)
    config_dir = Path(config_path).parent if config_path else Path.cwd()
    debounce = debounce_override if debounce_override is not None else cfg.watch_debounce

    # Collect all files to watch
    watch_files: set[Path] = set()
    for m in cfg.mappings:
        source_path = (config_dir / m.source).resolve()
        target_path = (config_dir / m.target).resolve()
        watch_files.add(source_path)
        watch_files.add(target_path)

    # Collect unique parent directories
    watch_dirs: set[Path] = {f.parent for f in watch_files}

    click.echo(f"👁️  consync watcher started (debounce={debounce}s)")
    click.echo(f"   Watching {len(watch_files)} files in {len(watch_dirs)} directory(s)")
    click.echo(f"   Press Ctrl+C to stop.\n")

    for f in sorted(watch_files):
        click.echo(f"   • {f.relative_to(config_dir) if f.is_relative_to(config_dir) else f}")
    click.echo("")

    # ── Startup sync: catch any drift from while watcher was not running ──
    click.echo("[startup] Running full sync to recover any drift...")
    try:
        reports = sync(config_path=config_path)
        for r in reports:
            if r.result in (SyncResult.SYNCED_SOURCE_TO_TARGET, SyncResult.SYNCED_TARGET_TO_SOURCE):
                click.echo(f"         ✅ {r.message}")
            elif r.result == SyncResult.ERROR:
                click.echo(f"         ❌ {r.message}")
        click.echo("[startup] Done.\n")
    except Exception as e:
        click.echo(f"[startup] ⚠️  Startup sync failed: {e} — continuing in watch mode.\n")

    # ── Event queue (thread-safe) — changes are QUEUED, never dropped ──
    pending_changes: dict[Path, str] = {}  # path → forced direction
    pending_lock = threading.Lock()
    last_sync_time: float = 0

    class SyncHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.is_directory:
                return

            changed_path = Path(event.src_path).resolve()
            if changed_path not in watch_files:
                return

            # Determine direction based on which file changed
            force = None
            for m in cfg.mappings:
                source_resolved = (config_dir / m.source).resolve()
                target_resolved = (config_dir / m.target).resolve()
                if changed_path == source_resolved:
                    force = "source"
                    break
                elif changed_path == target_resolved:
                    force = "target"
                    break

            # Queue the event (never drop)
            with pending_lock:
                pending_changes[changed_path] = force
                logger.debug("Queued: %s (direction=%s)", changed_path.name, force)

    def _process_queue():
        """Process all pending changes in one coalesced sync."""
        nonlocal last_sync_time

        with pending_lock:
            if not pending_changes:
                return
            # Snapshot and clear
            queued = dict(pending_changes)
            pending_changes.clear()

        # Determine overall force direction (if all queued point same way)
        directions = set(queued.values())
        if len(directions) == 1:
            force = directions.pop()
        else:
            force = None  # mixed — let engine auto-detect

        rel_names = [p.name for p in queued.keys()]
        timestamp = time.strftime("%H:%M:%S")
        click.echo(f"[{timestamp}] 📝 {', '.join(rel_names)} changed — syncing...")

        # Retry on lock conflict
        for attempt in range(LOCK_RETRY_ATTEMPTS):
            try:
                reports = sync(config_path=config_path, force_direction=force)
                for r in reports:
                    if r.result in (SyncResult.SYNCED_SOURCE_TO_TARGET, SyncResult.SYNCED_TARGET_TO_SOURCE):
                        click.echo(f"         ✅ {r.message}")
                    elif r.result == SyncResult.ALREADY_IN_SYNC:
                        pass  # silent
                    elif r.result == SyncResult.ERROR:
                        click.echo(f"         ❌ {r.message}")
                last_sync_time = time.time()
                return  # success
            except Exception as e:
                if "Another consync process" in str(e) and attempt < LOCK_RETRY_ATTEMPTS - 1:
                    click.echo(f"         🔒 Lock conflict — retrying in {LOCK_RETRY_DELAY}s... ({attempt+1}/{LOCK_RETRY_ATTEMPTS})")
                    time.sleep(LOCK_RETRY_DELAY)
                else:
                    click.echo(f"         ❌ Sync failed: {e}")
                    logger.error("Watch sync failed: %s", e)
                    return

    observer = Observer()
    handler = SyncHandler()

    for dir_path in watch_dirs:
        if dir_path.exists():
            observer.schedule(handler, str(dir_path), recursive=False)

    observer.start()
    try:
        while True:
            time.sleep(debounce)
            # After debounce, process any queued events
            _process_queue()
    finally:
        observer.stop()
        observer.join()
