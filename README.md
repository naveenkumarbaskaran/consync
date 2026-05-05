# consync

**Bidirectional constant synchronisation between spreadsheets and source code.**

Keep a single source of truth for hardware constants (resistor values, timing parameters, frequencies) and automatically generate type-safe declarations for C, Python, Rust, Verilog, and VHDL — or sync changes back from code to your spreadsheet.

[![PyPI version](https://img.shields.io/pypi/v/consync.svg)](https://pypi.org/project/consync/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Why consync?

In hardware/firmware projects, constants live in Excel spreadsheets (for EE review) **and** in source code (for compilation). Manual copy-paste introduces:

- **Precision loss** — Excel shows 6 digits, your code needs 17 for IEEE 754 fidelity
- **Drift** — spreadsheet updated, code forgotten (or vice versa)
- **Format friction** — same value needs different syntax in C, Verilog, Python, VHDL

consync eliminates all three: one command syncs constants with full precision in both directions.

## Quick Start

```bash
pip install consync
```

### 1. Initialise

```bash
cd your-project/
consync init
```

Creates `.consync.yaml`:

```yaml
mappings:
  - source: constants.xlsx
    target: constants.h
    direction: both
    precision: 17
    header_guard: HW_CONSTANTS_H
```

### 2. Sync

```bash
consync sync
```

Reads `constants.xlsx`, generates `constants.h`:

```c
#ifndef HW_CONSTANTS_H
#define HW_CONSTANTS_H

const double R_SENSE           = 1.9999999999910001;  /* Ohm | Current sense resistor */
const double R_PULLUP          = 4706;                /* Ohm | I2C pull-up resistor */
const double C_FILTER          = 4.783294e-07;        /* F | Input filter capacitor */
const double FREQ_SWITCH       = 299872.93847293;     /* Hz | Switching frequency */

#endif /* HW_CONSTANTS_H */
```

### 3. Watch (continuous)

```bash
consync watch
```

Auto-syncs on file change. Edit the spreadsheet → code updates. Edit the code → spreadsheet updates.

### 4. CI gate

```bash
consync check
```

Returns exit code 1 if code and spreadsheet are out of sync. Add to pre-commit hooks:

```bash
consync install-hook
```

## Supported Formats

### Sources (input)

| Format | Extension | Notes |
|--------|-----------|-------|
| Excel | `.xlsx` | Auto-detects column headers |
| CSV | `.csv`, `.tsv` | Auto-detects delimiter |
| JSON | `.json` | Flat, array, or nested |
| TOML | `.toml` | Flat or table-with-metadata |
| C Header | `.h` | For reverse sync (target → source) |

### Targets (output)

| Format | Extension | Features |
|--------|-----------|----------|
| C Header | `.h` | Header guards, `const double`, aligned, pipe-separated comments |
| Python | `.py` | Type annotations (`float`/`int`), inline comments |
| Rust | `.rs` | `pub const`, `f64`/`i64`, doc comments |
| Verilog | `.v` | `parameter real`, optional module wrapper |
| VHDL | `.vhd` | Package with `ieee.math_real`, typed constants |
| JSON | `.json` | Structured with `_meta` header |

## Precision Guarantee

consync uses **17 significant digits** by default — the minimum needed for IEEE 754 double-precision round-trip fidelity. This means:

```
Excel value:     1.9999999999910001
C output:        1.9999999999910001
Parse back:      1.9999999999910001  ← identical bits
```

Configure per mapping:
```yaml
precision: 6  # fewer digits for display-only targets
```

## Bidirectional Sync

consync tracks file hashes in `.consync.state.json` to detect which side changed:

| Source changed | Target changed | Action |
|:-:|:-:|---|
| ✓ | — | Source → Target |
| — | ✓ | Target → Source |
| ✓ | ✓ | Conflict (configurable: `source_wins`, `target_wins`, `fail`) |
| — | — | No-op |

## Configuration Reference

```yaml
# .consync.yaml
mappings:
  - source: constants.xlsx       # source file path
    target: hw_constants.h       # target file path
    direction: both              # source_to_target | target_to_source | both
    precision: 17                # significant digits (1-17)
    header_guard: HW_CONSTANTS_H # C header guard name
    module_name: design_params   # Verilog module / VHDL package name

  - source: timing.csv
    target: timing.py
    direction: source_to_target
    precision: 10
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `consync init` | Create `.consync.yaml` in current directory |
| `consync sync` | Sync all mappings |
| `consync sync --dry-run` | Preview changes without writing |
| `consync sync --force source` | Force source → target regardless of state |
| `consync check` | Verify sync (exit 1 if out of sync) |
| `consync watch` | Watch files and auto-sync on change |
| `consync install-hook` | Install git pre-commit hook |
| `consync status` | Show current sync state |

## Target Audiences

| Domain | Source | Targets |
|--------|--------|---------|
| **Embedded firmware** | Excel/CSV from EE team | C headers |
| **FPGA/ASIC design** | Excel from systems team | Verilog + VHDL |
| **Control systems** | Excel with tuning params | Python + C |
| **Scientific computing** | TOML config | Python + Rust |
| **Multi-language libs** | JSON master | C + Python + Rust |

## Development

```bash
git clone https://github.com/naveenkb142/consync.git
cd consync
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
