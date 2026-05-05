"""Tests for the sync engine and state management."""

import json
import textwrap
from pathlib import Path

import pytest

from consync.models import Constant, MappingConfig, SyncDirection
from consync.state import SyncState, compute_hash
from consync.sync import sync, check, SyncResult


@pytest.fixture
def sync_project(tmp_path):
    """Create a minimal consync project with config + source file."""
    # Create config
    config = tmp_path / ".consync.yaml"
    config.write_text(textwrap.dedent("""\
        mappings:
          - source: constants.csv
            target: constants.h
            direction: both
            precision: 17
            header_guard: TEST_H
    """))

    # Create source CSV
    csv_file = tmp_path / "constants.csv"
    csv_file.write_text("Name,Value,Unit,Description\nR_SENSE,1.999,Ohm,Sense resistor\nR_PULLUP,4706,Ohm,Pull-up\n")

    return tmp_path, config


class TestSyncState:
    def test_new_state_is_empty(self, tmp_path):
        state = SyncState(tmp_path / ".state.json")
        assert state.get_hash("key", "source") is None
        assert state.get_hash("key", "target") is None

    def test_set_and_get_hash(self, tmp_path):
        state = SyncState(tmp_path / ".state.json")
        state.set_hash("k1", "abc123", "def456")
        assert state.get_hash("k1", "source") == "abc123"
        assert state.get_hash("k1", "target") == "def456"

    def test_persists_to_file(self, tmp_path):
        state_file = tmp_path / ".state.json"
        state = SyncState(state_file)
        state.set_hash("k1", "aaa", "bbb")

        # Reload
        state2 = SyncState(state_file)
        assert state2.get_hash("k1", "source") == "aaa"

    def test_clear(self, tmp_path):
        state_file = tmp_path / ".state.json"
        state = SyncState(state_file)
        state.set_hash("k1", "aaa", "bbb")
        state.clear()
        assert state.get_hash("k1", "source") is None
        assert not state_file.exists()


class TestComputeHash:
    def test_same_data_same_hash(self):
        c1 = [Constant("A", 1.0), Constant("B", 2.0)]
        c2 = [Constant("A", 1.0), Constant("B", 2.0)]
        assert compute_hash(c1) == compute_hash(c2)

    def test_different_value_different_hash(self):
        c1 = [Constant("A", 1.0)]
        c2 = [Constant("A", 1.1)]
        assert compute_hash(c1) != compute_hash(c2)

    def test_metadata_ignored(self):
        c1 = [Constant("A", 1.0, unit="V", description="voltage")]
        c2 = [Constant("A", 1.0, unit="mV", description="different")]
        assert compute_hash(c1) == compute_hash(c2)

    def test_order_independent(self):
        # Hashes use sorted keys internally
        c1 = [Constant("A", 1.0), Constant("B", 2.0)]
        c2 = [Constant("B", 2.0), Constant("A", 1.0)]
        assert compute_hash(c1) == compute_hash(c2)


class TestSync:
    def test_first_sync_creates_target(self, sync_project):
        tmp_path, config = sync_project
        reports = sync(config_path=config)

        assert len(reports) == 1
        assert reports[0].result == SyncResult.SYNCED_SOURCE_TO_TARGET
        assert reports[0].count == 2

        # Target should exist now
        target = tmp_path / "constants.h"
        assert target.exists()
        content = target.read_text()
        assert "R_SENSE" in content
        assert "R_PULLUP" in content

    def test_second_sync_is_noop(self, sync_project):
        tmp_path, config = sync_project
        sync(config_path=config)
        reports = sync(config_path=config)

        assert reports[0].result == SyncResult.ALREADY_IN_SYNC

    def test_force_direction(self, sync_project):
        tmp_path, config = sync_project
        # First sync to create target
        sync(config_path=config)

        # Force target → source (even though nothing changed)
        reports = sync(config_path=config, force_direction="target")
        assert reports[0].result == SyncResult.SYNCED_TARGET_TO_SOURCE

    def test_dry_run(self, sync_project):
        tmp_path, config = sync_project
        reports = sync(config_path=config, dry_run=True)

        assert "DRY RUN" in reports[0].message
        # Target should NOT be created
        assert not (tmp_path / "constants.h").exists()


class TestCheck:
    def test_in_sync(self, sync_project):
        tmp_path, config = sync_project
        sync(config_path=config)

        reports = check(config_path=config)
        assert reports[0].result == SyncResult.ALREADY_IN_SYNC

    def test_out_of_sync(self, sync_project):
        tmp_path, config = sync_project
        sync(config_path=config)

        # Modify source
        csv_file = tmp_path / "constants.csv"
        csv_file.write_text("Name,Value,Unit,Description\nR_SENSE,2.0,Ohm,Changed\n")

        reports = check(config_path=config)
        assert reports[0].result == SyncResult.CONFLICT

    def test_missing_target(self, sync_project):
        tmp_path, config = sync_project
        # Don't sync first — target doesn't exist
        reports = check(config_path=config)
        assert reports[0].result == SyncResult.ERROR
