# consync

**Bidirectional constant synchronisation between spreadsheets and source code.**

This is the npm wrapper for the [`consync` Python package](https://pypi.org/project/consync/).

## Prerequisites

- Python 3.10+
- pip install consync

## Install

```bash
npm install consync
# or
npx consync sync
```

## Usage

```bash
npx consync init          # Create .consync.yaml
npx consync sync          # Sync all mappings
npx consync watch         # Auto-sync on file changes
npx consync diff          # Preview changes
npx consync check         # CI gate (exit 1 if out of sync)
npx consync recover --list  # List backup snapshots
```

## Why npm?

For teams using Node.js toolchains that want `consync` accessible via `npx` or as a project dependency alongside their existing package.json scripts.

The actual logic is in the Python package — this wrapper finds the installed `consync` CLI and delegates all commands.

## Full Documentation

See the [main repository](https://github.com/naveenkumarbaskaran/consync) for complete docs, examples, and FAQ.

## License

MIT
