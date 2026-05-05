"""CLI entry point — consync command-line interface.

Commands:
    consync init          Create a .consync.yaml template
    consync sync          Sync all mappings (auto-detect direction)
    consync sync --from source   Force direction
    consync watch         Watch files and auto-sync on changes
    consync check         CI mode — verify files are in sync (exit 1 if not)
    consync install-hook  Install git pre-commit hook
    consync status        Show current sync state
    consync log           Show recent audit log entries
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from consync import __version__


@click.group()
@click.version_option(__version__, prog_name="consync")
@click.option("-v", "--verbose", is_flag=True, help="Show INFO-level details.")
@click.option("--debug", is_flag=True, help="Show DEBUG-level details (very verbose).")
@click.pass_context
def main(ctx, verbose: bool, debug: bool):
    """consync — Bidirectional sync between spreadsheets and source code constants."""
    from consync.logging_config import setup_logging
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["debug"] = debug
    setup_logging(verbose=verbose, debug=debug)


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


@main.command(name="log")
@click.option("-n", "--lines", default=20, help="Number of recent entries to show.")
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON lines.")
def show_log(lines: int, as_json: bool):
    """Show recent sync audit log entries.

    Displays timestamp, user, direction, files, and synced values.
    Reads from .consync.audit.jsonl in the current directory.
    """
    from consync.logging_config import read_audit_log

    entries = read_audit_log(last_n=lines)
    if not entries:
        click.echo("No audit log entries found. Run 'consync sync' first.")
        return

    for entry in entries:
        if as_json:
            import json
            click.echo(json.dumps(entry, ensure_ascii=False))
            continue

        ts = entry.get("timestamp", "?")
        user = entry.get("user", "?")
        direction = entry.get("direction", "?")
        source = entry.get("source", "?")
        target = entry.get("target", "?")
        count = entry.get("count", 0)
        dry = " [DRY RUN]" if entry.get("dry_run") else ""

        click.echo(f"  {ts}  {user}  {direction}  {source} ↔ {target}  ({count} constants){dry}")

        # Show constant values
        constants = entry.get("constants", [])
        for c in constants:
            name = c.get("name", "?")
            value = c.get("value", "?")
            unit = c.get("unit", "")
            unit_str = f" {unit}" if unit else ""
            click.echo(f"    {name} = {value}{unit_str}")
        click.echo("")


@main.command(name="recover")
@click.option("--file", "filepath", default=None, help="File to recover (e.g., out.h).")
@click.option("--at", "timestamp", default=None, help="ISO timestamp to restore to.")
@click.option("--last", is_flag=True, help="Restore the most recent backup.")
@click.option("--list", "list_only", is_flag=True, help="List available backups without restoring.")
def recover_cmd(filepath: str | None, timestamp: str | None, last: bool, list_only: bool):
    """Recover a file from a previous backup snapshot.

    Before every sync, consync saves the previous version of the target file.
    Use this command to list available snapshots or restore one.

    Examples:
        consync recover --list
        consync recover --file config.h --list
        consync recover --file config.h --last
        consync recover --file config.h --at 2026-05-05T08:45:12
    """
    from consync.backup import list_backups, recover_file

    project_dir = Path.cwd()

    if list_only or (filepath is None and not last):
        # List mode
        file_path = Path(filepath) if filepath else None
        backups = list_backups(filepath=file_path, project_dir=project_dir)

        if not backups:
            click.echo("No backups found. Backups are created automatically during sync.")
            return

        click.echo(f"Available backups ({len(backups)} snapshots):\n")
        for b in backups:
            size_kb = b["size"] / 1024
            click.echo(f"  {b['timestamp']}  {b['file']:30s}  {size_kb:.1f} KB")
        click.echo(f"\nRestore with: consync recover --file <name> --at <timestamp>")
        return

    if filepath is None:
        click.echo("❌ Specify --file to recover (or use --list to see available backups).")
        sys.exit(1)

    file_path = Path(filepath)
    result = recover_file(file_path, timestamp=timestamp, last=last, project_dir=project_dir)

    if result:
        click.echo(f"✅ Restored {filepath}")
    else:
        click.echo(f"❌ No backup found for {filepath}. Use --list to see available snapshots.")
        sys.exit(1)


@main.command(name="diff")
@click.option("--config", "config_path", default=None, help="Path to .consync.yaml.")
@click.option("--from", "from_side", type=click.Choice(["source", "target"]), default=None,
              help="Force sync direction.")
@click.option("--color/--no-color", default=True, help="Colorize diff output.")
def diff_cmd(config_path: str | None, from_side: str | None, color: bool):
    """Preview what would change on next sync (unified diff).

    Shows a unified diff for each mapping that would be modified,
    without actually writing any files. Like --dry-run but with full diff.
    """
    import difflib
    import tempfile
    from consync.config import load_config
    from consync.sync import _config_dir, _resolve_path, _parse_file, _render_file, _determine_direction
    from consync.state import SyncState, compute_hash

    try:
        cfg = load_config(config_path)
    except FileNotFoundError as e:
        click.echo(f"❌ {e}")
        sys.exit(1)

    config_dir = _config_dir(config_path)
    state = SyncState(config_dir / cfg.state_file)
    any_changes = False

    for mapping in cfg.mappings:
        source_path = _resolve_path(mapping.source, config_dir)
        target_path = _resolve_path(mapping.target, config_dir)
        key = state.mapping_key(mapping.source, mapping.target)

        direction = _determine_direction(
            mapping, source_path, target_path, state, key, cfg.on_conflict, from_side
        )

        if direction is None or direction == "conflict":
            continue

        # Determine what file would be written
        if direction == "source":
            constants = _parse_file(source_path, mapping.source_format)
            dest_path = target_path
        else:
            constants = _parse_file(target_path, mapping.target_format)
            dest_path = source_path

        # Render to temp file to get the "new" content
        with tempfile.NamedTemporaryFile(mode="w", suffix=dest_path.suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            _render_file(constants, tmp_path, mapping.target_format if direction == "source" else mapping.source_format, mapping)
            new_content = tmp_path.read_text().splitlines(keepends=True)
        finally:
            tmp_path.unlink(missing_ok=True)

        # Get current content
        if dest_path.exists():
            old_content = dest_path.read_text().splitlines(keepends=True)
        else:
            old_content = []

        # Generate unified diff
        diff_lines = list(difflib.unified_diff(
            old_content, new_content,
            fromfile=f"a/{dest_path.name}",
            tofile=f"b/{dest_path.name}",
            lineterm="",
        ))

        if diff_lines:
            any_changes = True
            click.echo(f"--- {mapping.source} → {mapping.target} ---")
            for line in diff_lines:
                if color:
                    if line.startswith("+") and not line.startswith("+++"):
                        click.echo(click.style(line, fg="green"))
                    elif line.startswith("-") and not line.startswith("---"):
                        click.echo(click.style(line, fg="red"))
                    elif line.startswith("@@"):
                        click.echo(click.style(line, fg="cyan"))
                    else:
                        click.echo(line)
                else:
                    click.echo(line)
            click.echo("")

    if not any_changes:
        click.echo("✔️  No changes — all mappings already in sync.")


if __name__ == "__main__":
    main()
