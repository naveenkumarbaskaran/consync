# consync

**Bidirectional constant synchronisation between spreadsheets and source code.**

Keep a single source of truth for hardware constants (resistor values, timing parameters, frequencies) and automatically generate type-safe declarations for C/C++, C#, Python, Rust, Verilog, and VHDL — or sync changes back from code to your spreadsheet.

<p align="center">
  <img src="assets/demo.gif" alt="consync demo" width="720">
</p>

[![PyPI version](https://img.shields.io/pypi/v/consync.svg)](https://pypi.org/project/consync/)
[![CI](https://github.com/naveenkumarbaskaran/consync/actions/workflows/ci.yml/badge.svg)](https://github.com/naveenkumarbaskaran/consync/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           .consync.yaml                                  │
│                    (mappings, precision, options)                         │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │      Config Loader       │
                    │  (auto-detect formats)   │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                   │
     ┌────────▼───────┐  ┌──────▼──────┐  ┌────────▼───────┐
     │    Parsers      │  │   State     │  │   Renderers    │
     │                 │  │  Tracker    │  │                │
     │ • xlsx          │  │             │  │ • c_header     │
     │ • csv           │  │ MD5 hashes  │  │ • csharp       │
     │ • json          │  │ per-mapping │  │ • python       │
     │ • toml          │  │ in .json    │  │ • rust         │
     │ • c_header      │  │             │  │ • verilog      │
     └────────┬────────┘  └──────┬──────┘  │ • vhdl         │
              │                  │          │ • json          │
              │                  │          │ • csv           │
              │                  │          └────────┬────────┘
              └──────────────────┼───────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │      Sync Engine        │
                    │                         │
                    │ 1. Parse source & target │
                    │ 2. Compare hashes       │
                    │ 3. Detect direction     │
                    │ 4. Render to changed    │
                    │    side's format        │
                    │ 5. Update state hashes  │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                   │
     ┌────────▼───────┐  ┌──────▼──────┐  ┌────────▼───────┐
     │   CLI (click)   │  │  Watcher    │  │  Git Hooks     │
     │                 │  │ (watchdog)  │  │ (pre-commit)   │
     │ sync/check/     │  │ debounced   │  │ consync check  │
     │ watch/init/     │  │ auto-sync   │  │ exit 1 = block │
     │ status          │  │             │  │                │
     └─────────────────┘  └─────────────┘  └────────────────┘
```

### Data Flow

```
Source file ──parse──► list[Constant] ──render──► Target file
   .xlsx                  name: str                    .h
   .csv                   value: int|float             .cs
   .json                  unit: str                    .py
   .toml                  description: str             .rs
   .h                                                  .v / .vhd
```

**Every format is both a parser and/or a renderer.** This means:
- **Bootstrap from code**: Have a `.h` file but no spreadsheet? Set `direction: target_to_source` and consync will *create* the CSV/JSON for you.
- **Multiple targets from one source**: One `.xlsx` can generate `.h` + `.py` + `.v` simultaneously.
- **Multiple sources**: Track as many source↔target pairs as needed in one config.

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
| C Header | `.h` | Parses `const`, `#define`, hex/int/float |

### Targets (output)

| Format | Extension | Features |
|--------|-----------|----------|
| C Header | `.h` | `const` or `#define`, `static`, `stdint.h` types, hex |
| C# | `.cs` | `namespace`, `public static class`, XML doc comments |
| Python | `.py` | Type annotations (`float`/`int`), inline comments |
| Rust | `.rs` | `pub const`, `f64`/`i64`, doc comments |
| Verilog | `.v` | `parameter real`, optional module wrapper |
| VHDL | `.vhd` | Package with `ieee.math_real`, typed constants |
| JSON | `.json` | Structured with `_meta` header |
| CSV | `.csv` | Round-trip back to spreadsheet |

---

## Bootstrap from Existing Code

**Don't have a spreadsheet yet?** consync can create one from your existing source files.

If you already have a C header with constants and want to start tracking it:

```yaml
# .consync.yaml
mappings:
  - source: params.csv          # doesn't exist yet — will be created
    target: existing_params.h   # already exists with const declarations
    direction: target_to_source
```

```bash
consync sync
# ✅ params.csv ↔ existing_params.h: 12 constants synced (target → source)
```

consync parses the existing `.h` file, extracts all constants (name, value, unit, description from comments), and writes a fresh CSV. From that point forward, you have a spreadsheet to share with your EE team.

**Works with any parseable target:** `.h`, `.json`, `.csv`, `.toml` — anything consync has a parser for can bootstrap a new source.

---

## Multiple Mappings (One Source → Many Targets)

Track as many source↔target pairs as you need. Each mapping is independent — different directions, precision, and output options:

```yaml
# .consync.yaml
mappings:
  # EE team's spreadsheet → firmware header
  - source: params.xlsx
    target: firmware/params.h
    direction: source_to_target
    precision: 17
    output_style: const
    typed_ints: true

  # Same spreadsheet → Python simulation
  - source: params.xlsx
    target: sim/params.py
    direction: source_to_target
    precision: 10

  # Same spreadsheet → FPGA constraints
  - source: params.xlsx
    target: rtl/params.v
    direction: source_to_target
    module_name: hw_params

  # Different spreadsheet → C# test harness
  - source: test_vectors.csv
    target: tests/TestConstants.cs
    direction: source_to_target
    namespace: ECU.Tests
    class_name: BrakeParams

  # Legacy header → bootstrap a TOML config from it
  - source: legacy_config.toml
    target: legacy/old_module.h
    direction: target_to_source
```

`consync sync` processes **all** mappings in one pass. `consync check` verifies them all.

---

## Embedded / ECU Configuration

consync is built for embedded firmware engineers. The C header renderer supports:

### Output Styles

```yaml
output_style: const    # default: const double X = 1.5;
output_style: define   # preprocessor: #define X 1.5
```

**`const` output (default):**
```c
#include <stdint.h>

static const uint16_t  BRAKE_PRESSURE_MAX = 250;
static const double    BRAKE_GAIN         = 1.45;
```

**`#define` output:**
```c
#define BRAKE_PRESSURE_MAX  250
#define BRAKE_GAIN          1.45
#define HW_VERSION          0x0A03
```

### Static Const

```yaml
static_const: true   # adds 'static' keyword (internal linkage, header-safe)
```

### Typed Integers (stdint.h)

```yaml
typed_ints: true   # auto-selects smallest stdint type that fits
```

| Value Range | Generated Type |
|-------------|---------------|
| 0–255 | `uint8_t` |
| 0–65535 | `uint16_t` |
| 0–4294967295 | `uint32_t` |
| 0+ (larger) | `uint64_t` |
| -128–127 | `int8_t` |
| -32768–32767 | `int16_t` |
| -2147483648–2147483647 | `int32_t` |
| (larger signed) | `int64_t` |

Hex values are preserved: `0xFF03` stays `0xFF03` in output.

### Full Embedded Example

```yaml
mappings:
  - source: ecu_params.csv
    target: src/ecu_params.h
    direction: source_to_target
    precision: 17
    header_guard: ECU_PARAMS_H
    output_style: const
    static_const: true
    typed_ints: true
```

Generates:
```c
#ifndef ECU_PARAMS_H
#define ECU_PARAMS_H

#include <stdint.h>

static const uint8_t   BRAKE_PRESSURE_MAX = 250;      /* bar | Max hydraulic pressure */
static const uint16_t  CAN_MSG_ID         = 0x1A3;    /* – | Brake status CAN ID */
static const double    FILTER_CUTOFF      = 1200.5;   /* Hz | Low-pass filter cutoff */
static const int16_t   TEMP_OFFSET        = -40;      /* °C | Temperature sensor offset */

#endif /* ECU_PARAMS_H */
```

---

## Precision Guarantee

consync uses **17 significant digits** by default — the minimum needed for IEEE 754 double-precision round-trip fidelity:

```
Excel value:     1.9999999999910001
C output:        1.9999999999910001
Parse back:      1.9999999999910001  ← identical bits
```

Configure per mapping:
```yaml
precision: 6  # fewer digits for display-only targets
```

---

## Bidirectional Sync

consync tracks file hashes in `.consync.state.json` to detect which side changed:

| Source changed | Target changed | Action |
|:-:|:-:|---|
| ✓ | — | Source → Target |
| — | ✓ | Target → Source |
| ✓ | ✓ | Conflict (configurable: `source_wins`, `target_wins`, `fail`) |
| — | — | No-op |

---

## Configuration Reference

```yaml
# .consync.yaml
mappings:
  - source: constants.xlsx        # source file path (xlsx/csv/json/toml/h)
    target: hw_constants.h        # target file path (h/cs/py/rs/v/vhd/json/csv)
    direction: both               # source_to_target | target_to_source | both
    precision: 17                 # significant digits (1-17, default: 17)

    # ─── C Header options ───
    header_guard: HW_CONSTANTS_H  # #ifndef guard name
    output_style: const           # const (default) | define
    static_const: true            # adds 'static' keyword (default: false)
    typed_ints: true              # use stdint.h types (default: false)

    # ─── C# options ───
    namespace: MyCompany.Firmware # C# namespace
    class_name: EcuConstants      # C# class name (default: Constants)

    # ─── Verilog/VHDL options ───
    module_name: design_params    # Verilog module / VHDL package name
```

---

## Safety & Recovery

consync is designed for safety-critical embedded systems. Every sync is protected by:

### Automatic Backups

Before every write, the previous version is saved to `.consync/backups/`:

```
.consync/backups/
├── config.h.20260505_083012.bak
├── config.h.20260505_091045.bak
└── params.v.20260505_083012.bak
```

Retention: keeps last 20 backups per file (auto-trimmed).

### Recovery

Restore any file to a previous state:

```bash
# List all available snapshots
consync recover --list

# List snapshots for a specific file
consync recover --file config.h --list

# Restore most recent backup
consync recover --file config.h --last

# Restore to a specific timestamp
consync recover --file config.h --at 2026-05-05T08:30:12
```

Recovery creates a safety backup of the *current* state before restoring, so you can always undo an undo.

### Diff Preview

See exactly what would change before committing:

```bash
consync diff
```

Shows a colorized unified diff for each mapping that would be modified. Pair with `--from source` or `--from target` to preview forced-direction syncs.

### Validation Hooks

Define value constraints in `.consync.yaml` to reject out-of-range values **before** they reach your firmware:

```yaml
mappings:
  - source: calibration.xlsx
    target: brake_params.h
    direction: source_to_target
    validators:
      BRAKE_MAX_PRESSURE:
        min: 0
        max: 300
      TIMEOUT_MS:
        type: int
        min: 100
        max: 60000
      DEVICE_NAME:
        pattern: "^[A-Z]{3}-\\d{4}$"
      LOOKUP_TABLE:
        min_length: 4
        max_length: 256
        min: 0
        max: 1023
```

Supported validator rules:

| Rule | Applies to | Description |
|------|-----------|-------------|
| `min` / `max` | int, float, array elements | Numeric range (inclusive) |
| `type` | all | Expected type: `int`, `float`, `string` |
| `pattern` | string | Regex pattern (Python `re.match`) |
| `min_length` / `max_length` | arrays, strings | Length bounds |
| `not_empty` | all | Reject `""` or `[]` |

If validation fails, sync is **blocked** and the error is reported:

```
❌ calibration.xlsx ↔ brake_params.h: Validation failed: BRAKE_MAX_PRESSURE = 999 exceeds maximum 300
```

### Concurrency Lock

An advisory lock (`.consync.lock`) prevents concurrent writes:
- Detects stale locks from crashed processes (PID check + timeout)
- Auto-reclaims dead locks
- Prevents file corruption from parallel `consync sync` + `consync watch`

### Audit Log

Every sync is logged with full values to `.consync.audit.jsonl`:

```bash
# Show recent syncs with values
consync log

# Show last 5 entries as raw JSON
consync log -n 5 --json
```

Each entry records: timestamp, user, direction, files, all constant names+values — enabling full traceability for ISO 26262 / IEC 61508 compliance workflows.

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `consync init` | Create `.consync.yaml` in current directory |
| `consync sync` | Sync all mappings |
| `consync sync --dry-run` | Preview changes without writing |
| `consync sync --from source` | Force source → target regardless of state |
| `consync sync --from target` | Force target → source (bootstrap) |
| `consync check` | Verify sync (exit 1 if out of sync) |
| `consync watch` | Watch files and auto-sync on change |
| `consync diff` | Show unified diff of what would change |
| `consync recover --list` | List available snapshots |
| `consync recover --file X --last` | Restore most recent backup |
| `consync log` | Show audit log with values |
| `consync install-hook` | Install git pre-commit hook |
| `consync status` | Show current sync state |
| `-v` / `--verbose` | Show INFO-level details |
| `--debug` | Show DEBUG-level details |

---

## Target Audiences

| Domain | Source | Targets | Key Features |
|--------|--------|---------|--------------|
| **Embedded/ECU firmware** | Excel/CSV from EE team | C headers | `typed_ints`, `static_const`, `#define` |
| **FPGA/ASIC design** | Excel from systems team | Verilog + VHDL | `module_name`, `parameter real` |
| **Automotive (AUTOSAR)** | CSV with calibration data | C headers | Hex preservation, stdint.h |
| **.NET test harnesses** | CSV/JSON | C# classes | `namespace`, `class_name`, XML docs |
| **Control systems** | Excel with tuning params | Python + C | Full precision, bidirectional |
| **Multi-language libs** | JSON master | C + Python + Rust | One source, many targets |

---

## Development

```bash
git clone https://github.com/naveenkumarbaskaran/consync.git
cd consync
pip install -e ".[dev]"
pytest   # 151 tests
```

---

## License

MIT — see [LICENSE](LICENSE).
