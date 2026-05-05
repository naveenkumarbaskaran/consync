"""File watcher — auto-syncs when source or target files change.

Uses the `watchdog` library for cross-platform file system monitoring.
No `brew install` required — pure Python.
"""

from __future__ import annotations

import time
from pathlib import Path

import click

from consync.config import load_config
from consync.sync import sync, SyncResult


def start_watcher(
    config_path: str | Path | None = None,
    debounce_override: float | None = None,
):
    """Start watching all mapped files and auto-sync on changes.

    Blocks until KeyboardInterrupt.
    """
    from watchdog.events import FileSystemEventHandler, FileModifiedEvent
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

    last_sync: float = 0

    class SyncHandler(FileSystemEventHandler):
        def on_modified(self, event):
            nonlocal last_sync

            if event.is_directory:
                return

            changed_path = Path(event.src_path).resolve()
            if changed_path not in watch_files:
                return

            # Debounce
            now = time.time()
            if now - last_sync < debounce:
                return
            last_sync = now

            # Determine direction based on which file changed
            rel = changed_path.relative_to(config_dir) if changed_path.is_relative_to(config_dir) else changed_path
            timestamp = time.strftime("%H:%M:%S")
            click.echo(f"[{timestamp}] 📝 {rel} changed — syncing...")

            # Find which mapping this file belongs to and force direction
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

            try:
                reports = sync(config_path=config_path, force_direction=force)
                for r in reports:
                    if r.result in (SyncResult.SYNCED_SOURCE_TO_TARGET, SyncResult.SYNCED_TARGET_TO_SOURCE):
                        click.echo(f"         ✅ {r.message}")
                    elif r.result == SyncResult.ALREADY_IN_SYNC:
                        pass  # silent when already in sync
                    elif r.result == SyncResult.ERROR:
                        click.echo(f"         ❌ {r.message}")
            except Exception as e:
                click.echo(f"         ❌ Sync failed: {e}")

            # Update last_sync after processing to avoid re-trigger from generated file
            last_sync = time.time()

    observer = Observer()
    handler = SyncHandler()

    for dir_path in watch_dirs:
        if dir_path.exists():
            observer.schedule(handler, str(dir_path), recursive=False)

    observer.start()
    try:
        while True:
            time.sleep(0.5)
    finally:
        observer.stop()
        observer.join()
