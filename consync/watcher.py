"""File watcher — auto-syncs when source or target files change.

Uses the `watchdog` library for cross-platform file system monitoring.
No `brew install` required — pure Python.

Event handling:
  - Changes during debounce are QUEUED, not dropped
  - After debounce expires, all queued events are coalesced into one sync
  - Write suppression prevents ping-pong loops (sync-written files are
    ignored for a short window so they don't re-trigger sync)
  - Direction is NEVER forced — the state engine auto-detects which side
    changed using stored hashes, which correctly returns "already in sync"
    for files that were just written by the sync itself
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

# Write suppression: ignore events on files we just wrote for this duration (seconds).
# Must be longer than filesystem event propagation but shorter than user interaction.
WRITE_SUPPRESSION_WINDOW = 2.0


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
    click.echo("   Press Ctrl+C to stop.\n")

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
    pending_changes: dict[Path, str] = {}  # path → info about what changed
    pending_lock = threading.Lock()
    last_sync_time: float = 0

    # ── Write suppression — tracks files recently written by sync ──
    recently_written: dict[Path, float] = {}  # path → timestamp of sync write
    written_lock = threading.Lock()

    class SyncHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.is_directory:
                return

            changed_path = Path(event.src_path).resolve()
            if changed_path not in watch_files:
                return

            # Write suppression: skip events caused by sync's own writes
            with written_lock:
                written_time = recently_written.get(changed_path)
                if written_time and (time.time() - written_time) < WRITE_SUPPRESSION_WINDOW:
                    logger.debug(
                        "Suppressed event for %s (written %.1fs ago by sync)",
                        changed_path.name,
                        time.time() - written_time,
                    )
                    return

            # Queue the event (never drop). Don't force direction — let
            # the state engine auto-detect using stored hashes.
            with pending_lock:
                pending_changes[changed_path] = changed_path.name
                logger.debug("Queued: %s", changed_path.name)

    def _process_queue():
        """Process all pending changes in one coalesced sync."""
        nonlocal last_sync_time

        with pending_lock:
            if not pending_changes:
                return
            # Snapshot and clear
            queued = dict(pending_changes)
            pending_changes.clear()

        rel_names = [p.name for p in queued.keys()]
        timestamp = time.strftime("%H:%M:%S")
        click.echo(f"[{timestamp}] 📝 {', '.join(rel_names)} changed — syncing...")

        # Never force direction — let the state engine auto-detect which
        # side changed using stored hashes.  This prevents ping-pong:
        # after sync writes file B, B's hash matches the stored hash,
        # so the next cycle correctly detects "already in sync".

        # Retry on lock conflict
        for attempt in range(LOCK_RETRY_ATTEMPTS):
            try:
                reports = sync(config_path=config_path)
                for r in reports:
                    if r.result in (SyncResult.SYNCED_SOURCE_TO_TARGET, SyncResult.SYNCED_TARGET_TO_SOURCE):
                        click.echo(f"         ✅ {r.message}")
                        # Register written files for suppression so their
                        # filesystem events don't re-trigger another sync.
                        _suppress_written_files(r, config_dir)
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

    def _suppress_written_files(report, conf_dir):
        """Mark files written by sync for suppression so their events are ignored."""
        now = time.time()
        with written_lock:
            # Determine which file was written based on sync direction
            if report.result == SyncResult.SYNCED_SOURCE_TO_TARGET:
                # source → target: target was written
                written_path = (conf_dir / report.target).resolve()
                recently_written[written_path] = now
            elif report.result == SyncResult.SYNCED_TARGET_TO_SOURCE:
                # target → source: source was written
                written_path = (conf_dir / report.source).resolve()
                recently_written[written_path] = now

        # Prune old entries to prevent memory leak
        with written_lock:
            cutoff = now - WRITE_SUPPRESSION_WINDOW * 3
            stale = [p for p, t in recently_written.items() if t < cutoff]
            for p in stale:
                del recently_written[p]

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
