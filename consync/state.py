"""State management — hash-based change detection for sync.

Tracks MD5 hashes of constant data (name+value pairs) to detect which
side changed since last sync. This enables smart bidirectional sync:

    - If only source changed → sync source → target
    - If only target changed → sync target → source
    - If both changed → conflict (resolve per on_conflict setting)
    - If neither changed → skip (already in sync)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from consync.models import Constant


def _normalize_value(v):
    """Normalize a constant value for stable hashing.

    Ensures int/float equivalence: C produces 1.0 (float) for ``1.0F``,
    but Excel stores it as integer 1.  Without normalization these hash
    differently, causing perpetual "out of sync" after every round-trip.

    Rules:
      - int/float that are whole numbers → canonical float (``1.0``)
      - list values → each element normalized recursively
      - strings → unchanged
    """
    if isinstance(v, list):
        return [_normalize_value(x) for x in v]
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return v


def compute_hash(constants: list[Constant]) -> str:
    """Compute a stable hash of constant name+value pairs.

    Only hashes names and values (not unit/description) since those
    are the semantically meaningful content for sync detection.

    Uses a sorted list of (name, value) tuples instead of a dict to
    correctly handle duplicate constant names (e.g., multi-variant
    struct tables where Motor_X__R_Phase appears once per variant).
    A dict would silently discard all but the last duplicate, making
    edits to earlier variants invisible to change detection.

    Numeric values are normalized to float so that ``int 1`` and
    ``float 1.0`` hash identically — this is critical for xlsx
    round-trips where Excel drops the ``.0`` from whole numbers.
    """
    pairs = sorted(
        (c.name, _normalize_value(c.value)) for c in constants
    )
    key = json.dumps(pairs, default=str)
    return hashlib.md5(key.encode()).hexdigest()


class SyncState:
    """Persistent sync state stored in .consync.state.json."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self._data: dict = {}
        self._load()

    def _load(self):
        if self.state_file.exists():
            try:
                self._data = json.loads(self.state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def _save(self):
        self.state_file.write_text(json.dumps(self._data, indent=2) + "\n", encoding="utf-8")

    def get_hash(self, mapping_key: str, side: str) -> str | None:
        """Get the stored hash for a mapping side ('source' or 'target')."""
        entry = self._data.get(mapping_key, {})
        return entry.get(side)

    def set_hash(self, mapping_key: str, source_hash: str, target_hash: str):
        """Update stored hashes after a successful sync."""
        self._data[mapping_key] = {
            "source": source_hash,
            "target": target_hash,
        }
        self._save()

    def mapping_key(self, source: str, target: str) -> str:
        """Generate a stable key for a source/target pair."""
        return f"{source}::{target}"

    def clear(self):
        """Reset all state."""
        self._data = {}
        if self.state_file.exists():
            self.state_file.unlink()
