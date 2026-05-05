# consync — Build Plan

## Status: Phase 1 in progress (skeleton created)

### Completed
- [x] Directory structure created
- [x] `pyproject.toml` (hatchling, CLI entry point, dependencies)
- [x] `.gitignore`
- [x] `LICENSE` (MIT)

### Phase 1 — Core (next session)
- [ ] `consync/__init__.py` — public API (`sync()`, `watch()`, `init()`)
- [ ] `consync/models.py` — `Constant` dataclass, `SyncDirection` enum
- [ ] `consync/precision.py` — IEEE 754 formatting, configurable sig digits
- [ ] `consync/config.py` — `.consync.yaml` loader + schema validation
- [ ] `consync/state.py` — hash-based change detection (`.consync.state.json`)
- [ ] `consync/parsers/__init__.py` — parser registry
- [ ] `consync/parsers/xlsx.py` — Excel reader (from hw_constants/sync.py)
- [ ] `consync/parsers/csv_parser.py` — CSV reader
- [ ] `consync/parsers/json_parser.py` — JSON reader
- [ ] `consync/parsers/toml_parser.py` — TOML reader
- [ ] `consync/parsers/c_header.py` — C header reader (bidirectional)
- [ ] `consync/renderers/__init__.py` — renderer registry
- [ ] `consync/renderers/c_header.py` — `.h` writer (17-digit precision)
- [ ] `consync/renderers/python_const.py` — Python constants file
- [ ] `consync/renderers/rust_const.py` — Rust `const` declarations
- [ ] `consync/renderers/verilog.py` — Verilog `parameter` declarations
- [ ] `consync/renderers/vhdl.py` — VHDL `constant` declarations
- [ ] `consync/renderers/json_renderer.py` — JSON output
- [ ] `consync/cli.py` — Click CLI (`sync`, `watch`, `check`, `init`, `install-hook`)

### Phase 2 — Watcher
- [ ] `consync/watcher.py` — `watchdog`-based file watcher (cross-platform)
- [ ] Debounce logic (configurable, default 2s)
- [ ] Smart direction detection per event

### Phase 3 — Git Hooks + CI
- [ ] `consync/hooks.py` — `install-hook` (pre-commit auto-sync)
- [ ] `consync check` — CI verify mode (exit 1 if out of sync)
- [ ] Direction auto-detect from hash state

### Phase 4 — Polish
- [ ] `tests/` — unit tests for all parsers + renderers + precision
- [ ] `examples/hardware/` — Excel ↔ C header (your original use case)
- [ ] `examples/fpga/` — Excel ↔ Verilog/VHDL parameters
- [ ] `README.md` — full docs, badges, usage examples
- [ ] GitHub repo creation + initial push
- [ ] PyPI publish

---

## Key Design Decisions (locked in)

| Decision | Choice |
|----------|--------|
| Package name | `consync` |
| Data model | `Constant(name, value, unit, description)` — always tabular |
| Precision | Default 17 sig digits (IEEE 754 round-trip), configurable per mapping |
| Config format | `.consync.yaml` |
| CLI framework | Click |
| Watcher | Python `watchdog` (no `brew install` needed) |
| Sync directions | `source_to_target`, `target_to_source`, `both` |
| Conflict resolution | Source wins (configurable) |
| Scope | Numeric constants only (float/int + metadata). NOT a generic file sync tool. |

## Target Audience

| Audience | Their pain | consync solves |
|----------|-----------|----------------|
| Embedded/firmware engineers | Datasheet → C headers, decimal precision loss | xlsx → .h with 17-digit fidelity |
| PCB/ASIC designers | Component values in Excel, sim code in C/Verilog | xlsx → Verilog parameters |
| Control systems (automotive) | Calibration tables → ECU firmware | xlsx ↔ .h bidirectional |
| Scientific computing | Physical constants with full precision | xlsx/json → Python/C |
| FPGA engineers | Register maps, clock dividers in spreadsheets | xlsx → VHDL constants |

## File Structure (target)

```
consync/
├── pyproject.toml          ✅ done
├── LICENSE                 ✅ done
├── .gitignore              ✅ done
├── README.md
├── consync/
│   ├── __init__.py
│   ├── models.py
│   ├── precision.py
│   ├── config.py
│   ├── state.py
│   ├── sync.py
│   ├── watcher.py
│   ├── hooks.py
│   ├── cli.py
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── xlsx.py
│   │   ├── csv_parser.py
│   │   ├── json_parser.py
│   │   ├── toml_parser.py
│   │   └── c_header.py
│   └── renderers/
│       ├── __init__.py
│       ├── c_header.py
│       ├── python_const.py
│       ├── rust_const.py
│       ├── verilog.py
│       ├── vhdl.py
│       └── json_renderer.py
├── tests/
│   ├── test_precision.py
│   ├── test_parsers.py
│   ├── test_renderers.py
│   ├── test_sync.py
│   └── test_cli.py
└── examples/
    ├── hardware/           # Excel ↔ C header
    └── fpga/               # Excel ↔ Verilog/VHDL
```

## Reference

- Original prototype: `/Users/I572120/Documents/Area/WorkSpace/VScode/hw_constants/`
- Package pattern reference: `github-repos/TokenShield/`
- GitHub: `naveenkb142/consync`
