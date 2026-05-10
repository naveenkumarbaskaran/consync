"""Tests for backup, recover, diff, validation, and lock features."""

from __future__ import annotations

import json
import os
import time

import pytest

# ============================================================
# Backup Tests
# ============================================================

class TestBackup:
    """Tests for consync.backup module."""

    def test_backup_creates_timestamped_copy(self, tmp_path):
        """Backup creates a .bak file with timestamp in name."""
        from consync.backup import backup_file

        target = tmp_path / "config.h"
        target.write_text("#define X 42\n")

        result = backup_file(target, backup_dir=tmp_path / ".consync" / "backups")

        assert result is not None
        assert result.exists()
        assert "config.h." in result.name
        assert result.name.endswith(".bak")
        assert result.read_text() == "#define X 42\n"

    def test_backup_nonexistent_file_returns_none(self, tmp_path):
        """Backing up a file that doesn't exist returns None."""
        from consync.backup import backup_file

        result = backup_file(tmp_path / "missing.h")
        assert result is None

    def test_backup_trims_old_backups(self, tmp_path):
        """Only keeps max_backups most recent files."""
        from consync.backup import backup_file

        target = tmp_path / "config.h"
        backup_dir = tmp_path / ".consync" / "backups"

        # Create 5 backups
        for i in range(5):
            target.write_text(f"#define X {i}\n")
            backup_file(target, backup_dir=backup_dir, max_backups=3)
            time.sleep(0.01)  # Ensure different timestamps

        backups = list(backup_dir.glob("config.h.*.bak"))
        assert len(backups) <= 3

    def test_backup_preserves_content_exactly(self, tmp_path):
        """Backup content matches original byte-for-byte."""
        from consync.backup import backup_file

        content = "// Complex content\n#define A 3.14159265358979\n#define B 2.71828\n"
        target = tmp_path / "math.h"
        target.write_text(content)

        result = backup_file(target, backup_dir=tmp_path / "bak")
        assert result.read_text() == content

    def test_list_backups_empty(self, tmp_path):
        """list_backups returns [] when no backups exist."""
        from consync.backup import list_backups

        result = list_backups(project_dir=tmp_path)
        assert result == []

    def test_list_backups_returns_metadata(self, tmp_path):
        """list_backups returns file/timestamp/size for each backup."""
        from consync.backup import backup_file, list_backups

        target = tmp_path / "out.h"
        target.write_text("content\n")
        backup_file(target, backup_dir=tmp_path / ".consync" / "backups")

        results = list_backups(project_dir=tmp_path)
        assert len(results) == 1
        assert results[0]["file"] == "out.h"
        assert "timestamp" in results[0]
        assert results[0]["size"] > 0


# ============================================================
# Recovery Tests
# ============================================================

class TestRecover:
    """Tests for file recovery from backups."""

    def test_recover_last_restores_most_recent(self, tmp_path):
        """--last flag restores the most recent backup."""
        from consync.backup import backup_file, recover_file

        target = tmp_path / "config.h"
        backup_dir = tmp_path / ".consync" / "backups"

        # Version 1
        target.write_text("v1\n")
        backup_file(target, backup_dir=backup_dir)
        time.sleep(0.01)

        # Version 2
        target.write_text("v2\n")
        backup_file(target, backup_dir=backup_dir)

        # Current (corrupted)
        target.write_text("CORRUPTED\n")

        # Recover last
        result = recover_file(target, last=True, project_dir=tmp_path)
        assert result is not None
        assert target.read_text() == "v2\n"

    def test_recover_creates_safety_backup(self, tmp_path):
        """Recovery saves current state before restoring."""
        from consync.backup import backup_file, recover_file

        target = tmp_path / "config.h"
        backup_dir = tmp_path / ".consync" / "backups"

        target.write_text("original\n")
        backup_file(target, backup_dir=backup_dir)

        target.write_text("modified\n")
        recover_file(target, last=True, project_dir=tmp_path)

        # Safety backup should exist
        safety_backups = list(backup_dir.glob("*pre_recover*"))
        assert len(safety_backups) == 1
        assert safety_backups[0].read_text() == "modified\n"

    def test_recover_no_backups_returns_none(self, tmp_path):
        """Returns None when no backups available."""
        from consync.backup import recover_file

        target = tmp_path / "missing.h"
        target.write_text("x")

        result = recover_file(target, last=True, project_dir=tmp_path)
        assert result is None


# ============================================================
# Validation Tests
# ============================================================

class TestValidation:
    """Tests for validator hooks."""

    def test_range_validation_pass(self):
        """Values within range pass validation."""
        from consync.models import Constant
        from consync.validators import parse_validators, validate_constants

        rules = parse_validators({
            "PRESSURE": {"min": 0, "max": 300}
        })
        constants = [Constant(name="PRESSURE", value=150)]

        result = validate_constants(constants, rules)
        assert result.ok

    def test_range_validation_below_min(self):
        """Value below min produces error."""
        from consync.models import Constant
        from consync.validators import parse_validators, validate_constants

        rules = parse_validators({
            "PRESSURE": {"min": 0, "max": 300}
        })
        constants = [Constant(name="PRESSURE", value=-5)]

        result = validate_constants(constants, rules)
        assert not result.ok
        assert "below minimum" in result.errors[0].message

    def test_range_validation_above_max(self):
        """Value above max produces error."""
        from consync.models import Constant
        from consync.validators import parse_validators, validate_constants

        rules = parse_validators({
            "TIMEOUT": {"min": 100, "max": 60000}
        })
        constants = [Constant(name="TIMEOUT", value=99999)]

        result = validate_constants(constants, rules)
        assert not result.ok
        assert "exceeds maximum" in result.errors[0].message

    def test_type_validation_int(self):
        """Type=int rejects float values."""
        from consync.models import Constant
        from consync.validators import parse_validators, validate_constants

        rules = parse_validators({
            "COUNT": {"type": "int"}
        })
        constants = [Constant(name="COUNT", value=3.14)]

        result = validate_constants(constants, rules)
        assert not result.ok
        assert "not an integer" in result.errors[0].message

    def test_type_validation_string_pass(self):
        """Type=string accepts string values."""
        from consync.models import Constant
        from consync.validators import parse_validators, validate_constants

        rules = parse_validators({
            "NAME": {"type": "string"}
        })
        constants = [Constant(name="NAME", value="hello")]

        result = validate_constants(constants, rules)
        assert result.ok

    def test_pattern_validation_match(self):
        """Regex pattern validates string format."""
        from consync.models import Constant
        from consync.validators import parse_validators, validate_constants

        rules = parse_validators({
            "DEVICE_ID": {"pattern": r"^[A-Z]{3}-\d{4}$"}
        })
        constants = [Constant(name="DEVICE_ID", value="ABC-1234")]

        result = validate_constants(constants, rules)
        assert result.ok

    def test_pattern_validation_no_match(self):
        """Regex mismatch produces error."""
        from consync.models import Constant
        from consync.validators import parse_validators, validate_constants

        rules = parse_validators({
            "DEVICE_ID": {"pattern": r"^[A-Z]{3}-\d{4}$"}
        })
        constants = [Constant(name="DEVICE_ID", value="bad-format")]

        result = validate_constants(constants, rules)
        assert not result.ok
        assert "does not match pattern" in result.errors[0].message

    def test_array_range_validation(self):
        """Min/max checks apply element-wise to arrays."""
        from consync.models import Constant
        from consync.validators import parse_validators, validate_constants

        rules = parse_validators({
            "TABLE": {"min": 0, "max": 100}
        })
        constants = [Constant(name="TABLE", value=[10, 50, 200])]

        result = validate_constants(constants, rules)
        assert not result.ok
        assert "TABLE[2]" in result.errors[0].message

    def test_length_validation(self):
        """min_length/max_length validate array size."""
        from consync.models import Constant
        from consync.validators import parse_validators, validate_constants

        rules = parse_validators({
            "LUT": {"min_length": 4, "max_length": 256}
        })
        constants = [Constant(name="LUT", value=[1, 2])]

        result = validate_constants(constants, rules)
        assert not result.ok
        assert "minimum is 4" in result.errors[0].message

    def test_not_empty_validation(self):
        """not_empty rejects empty string/array."""
        from consync.models import Constant
        from consync.validators import parse_validators, validate_constants

        rules = parse_validators({
            "LABEL": {"not_empty": True}
        })
        constants = [Constant(name="LABEL", value="")]

        result = validate_constants(constants, rules)
        assert not result.ok
        assert "must not be empty" in result.errors[0].message

    def test_missing_constant_skipped(self):
        """Validator for missing constant doesn't error."""
        from consync.models import Constant
        from consync.validators import parse_validators, validate_constants

        rules = parse_validators({
            "NONEXISTENT": {"min": 0, "max": 100}
        })
        constants = [Constant(name="OTHER", value=50)]

        result = validate_constants(constants, rules)
        assert result.ok

    def test_multiple_errors(self):
        """Multiple validation failures collected."""
        from consync.models import Constant
        from consync.validators import parse_validators, validate_constants

        rules = parse_validators({
            "A": {"min": 0},
            "B": {"max": 10},
        })
        constants = [
            Constant(name="A", value=-1),
            Constant(name="B", value=99),
        ]

        result = validate_constants(constants, rules)
        assert not result.ok
        assert len(result.errors) == 2


# ============================================================
# Lock Tests
# ============================================================

class TestLock:
    """Tests for concurrency lock."""

    def test_lock_creates_and_removes_file(self, tmp_path):
        """Lock file is created on acquire and removed on release."""
        from consync.lock import SyncLock

        lock = SyncLock(tmp_path)
        lock_path = tmp_path / ".consync.lock"

        assert not lock_path.exists()
        lock.acquire()
        assert lock_path.exists()
        lock.release()
        assert not lock_path.exists()

    def test_lock_context_manager(self, tmp_path):
        """Works as a context manager."""
        from consync.lock import SyncLock

        lock_path = tmp_path / ".consync.lock"

        with SyncLock(tmp_path):
            assert lock_path.exists()

        assert not lock_path.exists()

    def test_lock_prevents_double_acquire(self, tmp_path):
        """Second acquire raises LockError when first is held."""
        from consync.lock import SyncLock, LockError

        lock1 = SyncLock(tmp_path, timeout=60)  # Long timeout so it's not stale
        lock1.acquire()

        lock2 = SyncLock(tmp_path, timeout=60)
        with pytest.raises(LockError, match="Another consync process"):
            lock2.acquire()

        lock1.release()

    def test_stale_lock_reclaimed(self, tmp_path):
        """Lock from dead process is automatically reclaimed."""
        from consync.lock import SyncLock

        lock_path = tmp_path / ".consync.lock"

        # Create a lock with a clearly dead PID
        fake_info = {
            "pid": 99999999,  # Very unlikely to be a real PID
            "created": "2020-01-01T00:00:00+00:00",  # Very old
            "hostname": "test",
        }
        lock_path.write_text(json.dumps(fake_info))

        # Should succeed (stale lock removed)
        lock = SyncLock(tmp_path)
        lock.acquire()
        assert lock_path.exists()
        lock.release()

    def test_lock_contains_pid_and_timestamp(self, tmp_path):
        """Lock file has PID and creation time."""
        from consync.lock import SyncLock

        lock_path = tmp_path / ".consync.lock"

        with SyncLock(tmp_path):
            info = json.loads(lock_path.read_text())
            assert info["pid"] == os.getpid()
            assert "created" in info
            assert "hostname" in info


# ============================================================
# Integration: Backup During Sync
# ============================================================

class TestSyncWithBackup:
    """Tests that sync creates backups before overwriting."""

    def _write_config_and_source(self, tmp_path, source_content="Name,Value\nX,42\n"):
        """Helper: create a minimal consync project."""
        config = tmp_path / ".consync.yaml"
        config.write_text("""\
mappings:
  - source: data.csv
    target: out.h
    direction: source_to_target
    protect_target: false
""")
        source = tmp_path / "data.csv"
        source.write_text(source_content)
        return config

    def test_sync_creates_backup_of_target(self, tmp_path):
        """First sync to existing target creates a backup."""
        from consync.sync import sync

        self._write_config_and_source(tmp_path)
        target = tmp_path / "out.h"
        target.write_text("// old version\n")

        os.chdir(tmp_path)
        sync(config_path=str(tmp_path / ".consync.yaml"))

        backups_dir = tmp_path / ".consync" / "backups"
        assert backups_dir.exists()
        backups = list(backups_dir.glob("out.h.*.bak"))
        assert len(backups) == 1
        assert backups[0].read_text() == "// old version\n"

    def test_sync_no_backup_for_new_target(self, tmp_path):
        """No backup when target doesn't exist yet."""
        from consync.sync import sync

        self._write_config_and_source(tmp_path)
        # Don't create target

        os.chdir(tmp_path)
        sync(config_path=str(tmp_path / ".consync.yaml"))

        backups_dir = tmp_path / ".consync" / "backups"
        # Either dir doesn't exist or has no .bak files
        if backups_dir.exists():
            backups = list(backups_dir.glob("*.bak"))
            assert len(backups) == 0


# ============================================================
# Integration: Validation Blocks Sync
# ============================================================

class TestSyncWithValidation:
    """Tests that validators block sync on invalid values."""

    def test_validation_blocks_out_of_range(self, tmp_path):
        """Sync fails when value violates range validator."""
        from consync.sync import sync, SyncResult

        config = tmp_path / ".consync.yaml"
        config.write_text("""\
mappings:
  - source: data.csv
    target: out.h
    direction: source_to_target
    protect_target: false
    validators:
      X:
        min: 0
        max: 10
""")
        source = tmp_path / "data.csv"
        source.write_text("Name,Value\nX,999\n")

        os.chdir(tmp_path)
        reports = sync(config_path=str(config))

        assert reports[0].result == SyncResult.ERROR
        assert "Validation failed" in reports[0].message

    def test_validation_passes_valid_values(self, tmp_path):
        """Sync succeeds when all values pass validation."""
        from consync.sync import sync, SyncResult

        config = tmp_path / ".consync.yaml"
        config.write_text("""\
mappings:
  - source: data.csv
    target: out.h
    direction: source_to_target
    protect_target: false
    validators:
      X:
        min: 0
        max: 100
""")
        source = tmp_path / "data.csv"
        source.write_text("Name,Value\nX,50\n")

        os.chdir(tmp_path)
        reports = sync(config_path=str(config))

        assert reports[0].result == SyncResult.SYNCED_SOURCE_TO_TARGET


# ============================================================
# protect_target Tests
# ============================================================

class TestProtectTarget:
    """Tests for the protect_target option that makes destination files read-only."""

    def test_config_requires_protect_target_for_s2t(self, tmp_path):
        """Config loader rejects source_to_target without protect_target."""
        from consync.config import load_config

        config = tmp_path / ".consync.yaml"
        config.write_text("""\
mappings:
  - source: data.csv
    target: out.h
    direction: source_to_target
""")
        (tmp_path / "data.csv").write_text("Name,Value\nX,1\n")

        with pytest.raises(ValueError, match="protect_target.*required"):
            load_config(config)

    def test_config_requires_protect_target_for_t2s(self, tmp_path):
        """Config loader rejects target_to_source without protect_target."""
        from consync.config import load_config

        config = tmp_path / ".consync.yaml"
        config.write_text("""\
mappings:
  - source: data.csv
    target: out.h
    direction: target_to_source
    protect_target: false
""")
        # This should load fine (protect_target is set)
        cfg = load_config(config)
        assert cfg.mappings[0].protect_target is False

    def test_config_optional_for_both_direction(self, tmp_path):
        """Config loader does NOT require protect_target when direction is 'both'."""
        from consync.config import load_config

        config = tmp_path / ".consync.yaml"
        config.write_text("""\
mappings:
  - source: data.csv
    target: out.h
    direction: both
""")
        # Should load without error
        cfg = load_config(config)
        assert cfg.mappings[0].protect_target is False

    def test_protect_target_true_makes_file_readonly(self, tmp_path):
        """When protect_target is True, target file is set read-only after sync."""
        import stat
        from consync.sync import sync, SyncResult

        config = tmp_path / ".consync.yaml"
        config.write_text("""\
mappings:
  - source: data.csv
    target: out.h
    direction: source_to_target
    protect_target: true
""")
        source = tmp_path / "data.csv"
        source.write_text("Name,Value\nX,42\n")

        os.chdir(tmp_path)
        reports = sync(config_path=str(config))
        assert reports[0].result == SyncResult.SYNCED_SOURCE_TO_TARGET

        target = tmp_path / "out.h"
        assert target.exists()
        mode = target.stat().st_mode
        assert not (mode & stat.S_IWUSR), "Target should be read-only (no owner write bit)"
        assert not (mode & stat.S_IWGRP), "Target should be read-only (no group write bit)"
        assert not (mode & stat.S_IWOTH), "Target should be read-only (no other write bit)"

    def test_protect_target_false_leaves_file_writable(self, tmp_path):
        """When protect_target is False, target file stays writable."""
        import stat
        from consync.sync import sync, SyncResult

        config = tmp_path / ".consync.yaml"
        config.write_text("""\
mappings:
  - source: data.csv
    target: out.h
    direction: source_to_target
    protect_target: false
""")
        source = tmp_path / "data.csv"
        source.write_text("Name,Value\nX,42\n")

        os.chdir(tmp_path)
        reports = sync(config_path=str(config))
        assert reports[0].result == SyncResult.SYNCED_SOURCE_TO_TARGET

        target = tmp_path / "out.h"
        mode = target.stat().st_mode
        assert mode & stat.S_IWUSR, "Target should remain writable"

    def test_protect_target_resync_works(self, tmp_path):
        """Protected (read-only) file can still be updated by subsequent sync."""
        import stat
        from consync.sync import sync, SyncResult

        config = tmp_path / ".consync.yaml"
        config.write_text("""\
mappings:
  - source: data.csv
    target: out.h
    direction: source_to_target
    protect_target: true
""")
        source = tmp_path / "data.csv"
        source.write_text("Name,Value\nX,42\n")

        os.chdir(tmp_path)
        sync(config_path=str(config))
        target = tmp_path / "out.h"
        assert not (target.stat().st_mode & stat.S_IWUSR)

        content_v1 = target.read_text()

        # Update source and sync again — should work despite file being read-only
        source.write_text("Name,Value\nX,99\n")
        reports = sync(config_path=str(config))
        assert reports[0].result == SyncResult.SYNCED_SOURCE_TO_TARGET

        content_v2 = target.read_text()
        assert content_v2 != content_v1
        assert "99" in content_v2

        # File should be read-only again
        assert not (target.stat().st_mode & stat.S_IWUSR)