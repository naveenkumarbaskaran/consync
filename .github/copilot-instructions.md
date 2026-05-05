# Copilot Instructions for consync

## What is consync?

A Python CLI that bidirectionally syncs constants between spreadsheets (xlsx/csv/json/toml)
and source code (C, C#, Python, Rust, Verilog, VHDL). Built for embedded/firmware engineers
who need full IEEE 754 precision (17 significant digits).

## Project Structure

```
consync/
├── cli.py              # Click CLI — init, sync, check, watch, diff, recover, log, status
├── sync.py             # Core engine — direction detection, backup, validate, render
├── config.py           # .consync.yaml loader + format auto-detect
├── models.py           # Constant, MappingConfig, ConsyncConfig dataclasses
├── state.py            # SyncState (MD5 hashes for change detection)
├── watcher.py          # File watcher — queues events, retries on lock, startup sync
├── hooks.py            # Git pre-commit hook installer
├── backup.py           # Timestamped snapshots + recovery
├── lock.py             # Advisory .consync.lock with stale-PID detection
├── validators.py       # Range/type/pattern/length checks
├── logging_config.py   # 3-layer: console, rotating file, audit JSONL
├── parsers/            # xlsx, csv, json, toml, c_header
└── renderers/          # c_header, csharp, python, rust, verilog, vhdl, json, csv
tests/
├── test_parsers.py     # Parser unit tests
├── test_renderers.py   # Renderer unit tests
├── test_sync.py        # Sync engine + state tests
├── test_arrays.py      # Array constant support tests
├── test_safety.py      # Backup, recover, validation, lock tests
└── ...
```

## Key Patterns

- **Universal model**: `Constant(name: str, value: int|float|str|list, unit: str, description: str)`
- **Every format is a parser AND/OR renderer** — enables bootstrap and round-trip
- **Safety-first for firmware**: backup before write, validate before render, lock during sync
- **Watcher queues events** — never drops changes, retries on lock conflict
- **Audit trail**: JSONL log with every constant value for traceability

## When Editing Code

1. **Adding a parser/renderer**: Register in `__init__.py` of the package + add to `EXTENSION_TO_FORMAT` in `config.py`
2. **Adding CLI command**: Use `@main.command()` in `cli.py`, lazy imports inside function
3. **Modifying sync behavior**: Ensure backup + validation + lock flow is preserved
4. **Running tests**: `pytest tests/ -v` (151+ tests, takes ~0.5s)

## Constraints

- Python >=3.10
- Minimal deps: openpyxl, click, watchdog, pyyaml
- Precision: 17 significant digits default (IEEE 754 round-trip fidelity)
- Never drop file changes in watcher (queue + coalesce)
- Lock must be held during all write operations
- Backup must exist before overwriting any file

## Config Example (.consync.yaml)

```yaml
mappings:
  - source: calibration.xlsx
    target: firmware/config.h
    direction: source_to_target
    precision: 17
    header_guard: CONFIG_H
    static_const: true
    typed_ints: true
    validators:
      BRAKE_PRESSURE:
        min: 0
        max: 300
      TIMEOUT_MS:
        type: int
        min: 100
```

## CLI Command Reference

| Command | Purpose |
|---------|---------|
| `consync init` | Create .consync.yaml template |
| `consync sync` | Sync all mappings |
| `consync sync --dry-run` | Show what would be synced |
| `consync sync --from source` | Force direction |
| `consync check` | CI gate — exit 1 if out of sync |
| `consync watch` | File watcher with auto-sync |
| `consync diff` | Unified diff preview |
| `consync recover --list` | List backup snapshots |
| `consync recover --file X --last` | Restore most recent backup |
| `consync log` | Show audit trail with values |
| `consync install-hook` | Install git pre-commit hook |
| `consync status` | Show sync state per mapping |
