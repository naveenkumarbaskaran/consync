"""CLI entry point — consync command-line interface.

Commands:
    consync init          Create a .consync.yaml template
    consync sync          Sync all mappings (auto-detect direction)
    consync sync --from source   Force direction
    consync watch         Watch files and auto-sync on changes
    consync check         CI mode — verify files are in sync (exit 1 if not)
    consync install-hook  Install git pre-commit hook
    consync status        Show current sync state
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from consync import __version__


@click.group()
@click.version_option(__version__, prog_name="consync")
def main():
    """consync — Bidirectional sync between spreadsheets and source code constants."""
    pass


@main.command()
@click.option("--path", default=".", help="Directory to create .consync.yaml in.")
def init(path: str):
    """Create a .consync.yaml configuration template."""
    from consync.config import generate_default_config, DEFAULT_CONFIG_NAME

    target = Path(path) / DEFAULT_CONFIG_NAME
    if target.exists():
        click.echo(f"⚠️  {target} already exists. Delete it first to regenerate.")
        sys.exit(1)

    target.write_text(generate_default_config())
    click.echo(f"✅ Created {target}")
    click.echo(f"   Edit it to configure your source ↔ target mappings.")
    click.echo(f"   Then run: consync sync")


@main.command(name="sync")
@click.option("--from", "from_side", type=click.Choice(["source", "target"]), default=None,
              help="Force sync direction.")
@click.option("--dry-run", is_flag=True, help="Show what would change without writing files.")
@click.option("--config", "config_path", default=None, help="Path to .consync.yaml.")
def sync_cmd(from_side: str | None, dry_run: bool, config_path: str | None):
    """Sync constants between source and target files."""
    from consync.sync import sync, SyncResult

    try:
        reports = sync(config_path=config_path, force_direction=from_side, dry_run=dry_run)
    except FileNotFoundError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)
    except ValueError as e:
        click.echo(f"❌ Config error: {e}")
        sys.exit(1)

    has_errors = False
    for r in reports:
        icon = _result_icon(r.result)
        click.echo(f"{icon} {r.source} ↔ {r.target}: {r.message}")
        if r.result == SyncResult.ERROR:
            has_errors = True

    if has_errors:
        sys.exit(1)


@main.command()
@click.option("--config", "config_path", default=None, help="Path to .consync.yaml.")
def check(config_path: str | None):
    """Verify all mappings are in sync (CI mode). Exits 1 if out of sync."""
    from consync.sync import check as check_sync, SyncResult

    try:
        reports = check_sync(config_path=config_path)
    except FileNotFoundError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)

    all_ok = True
    for r in reports:
        icon = _result_icon(r.result)
        click.echo(f"{icon} {r.source} ↔ {r.target}: {r.message}")
        if r.result != SyncResult.ALREADY_IN_SYNC:
            all_ok = False

    if all_ok:
        click.echo(f"\n✅ All mappings in sync.")
    else:
        click.echo(f"\n❌ Out of sync! Run 'consync sync' to fix.")
        sys.exit(1)


@main.command()
@click.option("--config", "config_path", default=None, help="Path to .consync.yaml.")
@click.option("--debounce", default=None, type=float, help="Debounce seconds (default from config).")
def watch(config_path: str | None, debounce: float | None):
    """Watch source/target files and auto-sync on changes."""
    from consync.watcher import start_watcher

    try:
        start_watcher(config_path=config_path, debounce_override=debounce)
    except FileNotFoundError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\n👋 Watcher stopped.")


@main.command(name="install-hook")
@click.option("--hook", type=click.Choice(["pre-commit", "pre-push"]), default="pre-commit",
              help="Which git hook to install.")
def install_hook(hook: str):
    """Install a git hook that runs 'consync check' before commit/push."""
    from consync.hooks import install_git_hook

    try:
        install_git_hook(hook)
    except FileNotFoundError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)


@main.command()
@click.option("--config", "config_path", default=None, help="Path to .consync.yaml.")
def status(config_path: str | None):
    """Show current sync state for all mappings."""
    from consync.config import load_config
    from consync.state import SyncState

    try:
        cfg = load_config(config_path)
    except FileNotFoundError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)

    config_dir = Path(config_path).parent if config_path else Path.cwd()
    state = SyncState(config_dir / cfg.state_file)

    click.echo(f"Config: {config_path or '.consync.yaml'}")
    click.echo(f"State file: {cfg.state_file}")
    click.echo(f"Mappings: {len(cfg.mappings)}")
    click.echo("")

    for m in cfg.mappings:
        key = state.mapping_key(m.source, m.target)
        src_hash = state.get_hash(key, "source") or "unknown"
        tgt_hash = state.get_hash(key, "target") or "unknown"
        click.echo(f"  {m.source} ↔ {m.target}")
        click.echo(f"    Direction: {m.direction.value}")
        click.echo(f"    Precision: {m.precision} sig digits")
        click.echo(f"    Source hash: {src_hash[:8]}...")
        click.echo(f"    Target hash: {tgt_hash[:8]}...")
        click.echo("")


def _result_icon(result) -> str:
    from consync.sync import SyncResult
    return {
        SyncResult.SYNCED_SOURCE_TO_TARGET: "✅",
        SyncResult.SYNCED_TARGET_TO_SOURCE: "✅",
        SyncResult.ALREADY_IN_SYNC: "✔️ ",
        SyncResult.CONFLICT: "⚠️ ",
        SyncResult.SKIPPED: "⏭️ ",
        SyncResult.ERROR: "❌",
    }.get(result, "?")


if __name__ == "__main__":
    main()
