# consync — AI Assistant Instructions (CLAUDE.md)

## Project Overview

**consync** is a pip-installable Python CLI for bidirectional synchronisation between
spreadsheets (xlsx/csv/json/toml) and source code constant declarations (C, C#, Python,
Rust, Verilog, VHDL). It preserves full IEEE 754 precision (17 significant digits) and
supports embedded/firmware workflows.

**Repo:** https://github.com/naveenkumarbaskaran/consync  
**Author:** Naveen Kumar Baskaran (naveenkb142@gmail.com)  
**Python:** >=3.10  
**Build:** hatchling  
**CLI:** Click  

---

## Architecture

```
.consync.yaml  →  Config Loader  →  Sync Engine  →  State Tracker (.consync.state.json)
                       ↓                  ↓
               ┌──────────────┐    ┌──────────────┐
               │   Parsers    │    │  Renderers   │
               │ xlsx csv json│    │ c_header csv │
               │ toml c_header│    │ csharp python│
               └──────────────┘    │ rust verilog │
                                   │ vhdl json    │
                                   └──────────────┘
```

**Key design:** Every format can be both parser AND renderer. This enables bootstrap
(create spreadsheet from existing code) and round-trip (code → spreadsheet → code).

---

## Module Map

| File | Purpose |
|------|---------|
| `consync/cli.py` | Click CLI entry point — all commands |
| `consync/sync.py` | Core sync engine — direction detection, orchestration |
| `consync/config.py` | YAML config loader, format auto-detection |
| `consync/models.py` | `Constant`, `MappingConfig`, `ConsyncConfig` dataclasses |
| `consync/state.py` | `SyncState` — MD5 hashes per-mapping for change detection |
| `consync/watcher.py` | File watcher with debounce, queue, lock-retry |
| `consync/hooks.py` | Git hook installer |
| `consync/backup.py` | Auto-snapshot before every write + recovery |
| `consync/lock.py` | Advisory `.consync.lock` with stale-PID detection |
| `consync/validators.py` | User-defined value constraints (range/type/pattern) |
| `consync/logging_config.py` | 3-layer logging (console, file, audit JSONL) |
| `consync/parsers/` | One module per input format |
| `consync/renderers/` | One module per output format |

---

## Conventions

- **Dataclass-centric**: All data flows through `Constant(name, value, unit, description, metadata)`
- **No global state**: Config/state passed explicitly; watcher is the only stateful entry point
- **Format string IDs**: `"xlsx"`, `"csv"`, `"c_header"`, `"csharp"`, `"python"`, `"rust"`, `"verilog"`, `"vhdl"`, `"json"`, `"toml"`
- **Tests**: pytest, grouped by feature in `tests/`. Run with `pytest tests/ -v`
- **Logging**: Use `logger = logging.getLogger(__name__)` in every module. Audit via `write_audit_entry()`

---

## Adding a New Parser

1. Create `consync/parsers/my_format.py` with function `parse(filepath: Path) -> list[Constant]`
2. Register in `consync/parsers/__init__.py` → `PARSERS` dict
3. Add extension mapping in `consync/config.py` → `EXTENSION_TO_FORMAT`
4. Add tests in `tests/test_parsers.py`

## Adding a New Renderer

1. Create `consync/renderers/my_format.py` with function `render(constants: list[Constant], filepath: Path, config: MappingConfig)`
2. Register in `consync/renderers/__init__.py` → `RENDERERS` dict
3. Add extension mapping in `consync/config.py` → `EXTENSION_TO_FORMAT`
4. Add tests in `tests/test_renderers.py`

---

## Safety Features (Critical for Embedded)

| Feature | Module | Behaviour |
|---------|--------|-----------|
| **Backup** | `backup.py` | Copies target to `.consync/backups/` before every write. Retains 20/file. |
| **Recovery** | `backup.py` + CLI `recover` | Restore any file by timestamp. Creates safety backup before restoring. |
| **Validation** | `validators.py` | Blocks sync if values violate `validators:` rules in config. |
| **Lock** | `lock.py` | Advisory PID-based lock prevents concurrent writes. Auto-reclaims stale. |
| **Audit** | `logging_config.py` | Every sync logged with timestamp, user, direction, all values. |
| **Queue** | `watcher.py` | Events during debounce are queued (never dropped). Lock conflicts retried 3x. |
| **Startup sync** | `watcher.py` | On `consync watch`, a full sync runs first to recover any drift. |

---

## Common Tasks

### Run tests
```bash
cd /path/to/consync
pip install -e ".[dev]"
pytest tests/ -v
```

### Run a specific test file
```bash
pytest tests/test_safety.py -v
```

### Test the CLI manually
```bash
cd examples/
consync sync --dry-run
consync diff
consync log -n 5
consync recover --list
```

### Add a new CLI command
1. Add function with `@main.command()` decorator in `cli.py`
2. Follow pattern: import lazily inside function, handle errors, call `sys.exit(1)` on failure

---

## Do NOT

- Put secrets/credentials in any file (there are none in this project)
- Modify `pyproject.toml` build config without testing `pip install -e .`
- Break round-trip precision (17 sig digits must survive parse→render→parse)
- Remove the lock/backup from sync.py — these are safety-critical for firmware engineers
- Add heavy dependencies (keep it lightweight: openpyxl, click, watchdog, pyyaml only)
