# FAQ — Frequently Asked Questions

## General

### What is consync?

A Python CLI that bidirectionally syncs constants between spreadsheets (xlsx/csv/json/toml) and source code constant declarations (C, C#, Python, Rust, Verilog, VHDL). One source of truth, many outputs — with full IEEE 754 precision.

### Who is it for?

- Embedded firmware engineers (ECU calibration, FPGA parameters)
- Hardware/software teams sharing constants via Excel
- Any project where the same constant appears in multiple languages
- Teams needing ISO 26262 / IEC 61508 traceability of parameter changes

### How do I install it?

```bash
pip install consync
```

Requires Python >=3.10. No system dependencies.

---

## Sync Behaviour

### What happens when both files change? (Conflict)

By default, `on_conflict: source_wins` — the spreadsheet takes priority. Configurable:

```yaml
on_conflict: source_wins    # default
on_conflict: target_wins    # code takes priority
on_conflict: fail           # error, manual resolution required
```

Or override per-sync: `consync sync --from source`

### Does consync modify my source file?

Only in bidirectional mode (`direction: both`) or `target_to_source` mode when the target changed. In the common `source_to_target` mode, your spreadsheet is never touched.

### What if I want to bootstrap a spreadsheet from existing code?

Set `direction: target_to_source` with the code file as target:

```yaml
mappings:
  - source: params.csv        # doesn't exist yet
    target: legacy/config.h   # existing code
    direction: target_to_source
```

Run `consync sync` — it creates `params.csv` from the code.

---

## Watcher

### What happens to changes during the debounce window?

**They are queued, never dropped.** Events that arrive during the debounce period accumulate in a thread-safe queue. Once debounce expires, all queued events are coalesced into a single sync operation.

### What if the lock is held when the watcher tries to sync?

The watcher retries up to 3 times (2-second delay between attempts). If all retries fail, the error is logged and the watcher continues watching — the next file change will trigger a new sync attempt.

### If the watcher was stopped and files drifted, how do I recover?

On startup, `consync watch` runs a **full sync automatically** to catch any drift that occurred while the watcher was down. You can also manually force a sync at any time:

```bash
consync sync                   # auto-detect direction
consync sync --from source     # force spreadsheet → code
```

### Can I run the watcher and manual sync simultaneously?

Yes, but they share the same advisory lock. If you run `consync sync` while the watcher is processing, one will wait (watcher retries, CLI may briefly block). This is by design — prevents file corruption.

---

## Safety & Recovery

### If something goes wrong, can I recover?

**Yes.** Every sync creates a timestamped backup before writing:

```bash
# See what backups exist
consync recover --list

# Restore the most recent version
consync recover --file config.h --last

# Restore to a specific point in time
consync recover --file config.h --at 2026-05-05T08:30:12
```

Recovery itself creates a safety backup first, so you can always "undo the undo."

### Where are backups stored?

`.consync/backups/` in your project root. Each file gets timestamped copies:

```
.consync/backups/
├── config.h.20260505_083012.bak
├── config.h.20260505_091045.bak
└── params.v.20260505_083012.bak
```

Last 20 backups per file are kept (auto-trimmed).

### How do I preview changes before syncing?

```bash
consync diff
```

Shows a colorized unified diff of what would be written — without actually changing files.

### Can I validate values before they reach firmware?

Yes — define constraints in `.consync.yaml`:

```yaml
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
```

If validation fails, the sync is **blocked** — no file is written. Errors are reported clearly.

### What is `.consync.lock`?

An advisory lock file that prevents two processes from writing simultaneously. Contains the PID and timestamp of the holding process. Automatically reclaimed if the process is dead (stale lock detection).

### Can I see what was synced and when?

```bash
consync log                  # human-readable recent syncs
consync log -n 50 --json     # raw JSONL for scripting
```

Each entry includes: timestamp, user, direction, files, and **all constant values** — full audit trail.

---

## Precision

### Why 17 significant digits?

IEEE 754 double-precision requires exactly 17 significant decimal digits for bit-exact round-trip:

```
Input:  1.9999999999910001
Output: 1.9999999999910001  ← identical bits after parse→render→parse
```

Fewer digits risk precision loss. Configure per-mapping: `precision: 6` for display-only targets.

### Does consync preserve hex values?

Yes. `0xFF03` stays `0xFF03` in C output. Hex integers are detected and preserved through the entire pipeline.

---

## Arrays

### Can I sync array/table constants?

Yes. Arrays are supported across the entire stack:

**In CSV** (pipe-delimited):
```csv
Name,Value,Unit,Description
LOOKUP_TABLE,10|20|30|40,,Calibration lookup
```

**In JSON**:
```json
{"LOOKUP_TABLE": [10, 20, 30, 40]}
```

**Generated C output**:
```c
static const int32_t LOOKUP_TABLE[] = {10, 20, 30, 40};
```

Also works in C#, Python, Rust renderers. Validators can check array element ranges and length.

---

## CI / Git Integration

### How do I gate commits on sync status?

```bash
consync install-hook   # installs pre-commit hook
```

Or add to CI:
```yaml
- run: pip install consync
- run: consync check   # exits 1 if out of sync
```

### Does it work with monorepos?

Yes. `consync sync` walks up from CWD to find `.consync.yaml` (like `.gitignore`). Multiple independent configs in different subdirectories work fine.

---

## Configuration

### What formats can I use as source?

xlsx, csv, json, toml, or C header files. Anything with a parser can be a source.

### Can one source generate multiple outputs?

Yes — add multiple mappings:

```yaml
mappings:
  - source: params.xlsx
    target: firmware/config.h
  - source: params.xlsx
    target: sim/config.py
  - source: params.xlsx
    target: fpga/params.v
```

All processed in one `consync sync` pass.

### What are all the C header options?

| Option | Default | Description |
|--------|---------|-------------|
| `output_style` | `"const"` | `"const"` or `"define"` (#define macros) |
| `static_const` | `false` | Adds `static` keyword (header-safe) |
| `typed_ints` | `true` | Uses `uint8_t`/`int32_t`/etc. from `<stdint.h>` |
| `header_guard` | auto | `#ifndef` guard name |

---

## Troubleshooting

### `consync sync` says "Lock conflict"

Another consync process is running (or crashed). Check:

```bash
cat .consync.lock   # shows PID and timestamp
```

If the PID is dead, delete the lock file: `rm .consync.lock`

The watcher auto-detects stale locks (dead PID or >30s old) and reclaims them.

### `consync check` exits 1 but I just ran sync

Your git hook or CI might be running in a different directory. Ensure `.consync.yaml` is findable from where the command runs, or pass `--config path/to/.consync.yaml`.

### My values lose precision

Check your `precision` setting in `.consync.yaml`. Default is 17 (full IEEE 754). If you previously set a lower value, increase it.

### The watcher doesn't detect changes to my .xlsx file

Some editors (Excel, LibreOffice) write to temp files then rename. The watcher monitors the final path — the rename should trigger a modified event. If not, try saving twice or increasing `watch_debounce` to give the editor time to finalize.
