"""Git hook installer — adds consync check to pre-commit or pre-push."""

from __future__ import annotations

from pathlib import Path

import click


HOOK_TEMPLATE = """\
#!/usr/bin/env bash
# consync — auto-generated git hook
# Verifies constants are in sync before {hook_type}.
# To skip: git {git_cmd} --no-verify

set -euo pipefail

if command -v consync &> /dev/null; then
    echo "🔍 consync: checking sync state..."
    if ! consync check; then
        echo ""
        echo "❌ Constants out of sync! Run 'consync sync' first."
        exit 1
    fi
    echo "✅ consync: all constants in sync."
else
    echo "⚠️  consync not installed — skipping sync check."
    echo "   Install with: pip install consync"
fi
"""


def install_git_hook(hook_type: str = "pre-commit"):
    """Install a git hook that runs 'consync check'.

    Args:
        hook_type: "pre-commit" or "pre-push"

    Raises:
        FileNotFoundError: If not in a git repository.
    """
    git_dir = _find_git_dir()
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    hook_file = hooks_dir / hook_type

    git_cmd = "commit" if hook_type == "pre-commit" else "push"

    # Check for existing hook
    if hook_file.exists():
        existing = hook_file.read_text()
        if "consync" in existing:
            click.echo(f"✔️  consync hook already installed in .git/hooks/{hook_type}")
            return

        # Append to existing hook
        click.echo(f"⚠️  Existing {hook_type} hook found — appending consync check.")
        with open(hook_file, "a") as f:
            f.write("\n\n# --- consync sync check ---\n")
            f.write(HOOK_TEMPLATE.format(hook_type=hook_type, git_cmd=git_cmd))
    else:
        # Create new hook
        hook_file.write_text(HOOK_TEMPLATE.format(hook_type=hook_type, git_cmd=git_cmd))

    hook_file.chmod(0o755)
    click.echo(f"✅ Installed consync check in .git/hooks/{hook_type}")
    click.echo(f"   Will run 'consync check' before every {git_cmd}.")
    click.echo(f"   Skip with: git {git_cmd} --no-verify")


def _find_git_dir() -> Path:
    """Find the .git directory by walking up from CWD."""
    cwd = Path.cwd()
    for directory in [cwd, *cwd.parents]:
        git_dir = directory / ".git"
        if git_dir.is_dir():
            return git_dir
    raise FileNotFoundError(
        "Not a git repository. Run this command from within a git repo."
    )
