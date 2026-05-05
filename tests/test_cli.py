"""Tests for CLI commands."""

import textwrap
from pathlib import Path

import pytest
from click.testing import CliRunner

from consync.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def project_dir(tmp_path):
    """Create a temp project with config + data."""
    config = tmp_path / ".consync.yaml"
    config.write_text(textwrap.dedent("""\
        mappings:
          - source: data.csv
            target: out.h
            direction: source_to_target
            precision: 17
            header_guard: TEST_H
    """))
    csv = tmp_path / "data.csv"
    csv.write_text("Name,Value,Unit\nPI,3.14159,rad\nE,2.71828,\n")
    return tmp_path


class TestInitCommand:
    def test_creates_config(self, runner, tmp_path):
        result = runner.invoke(main, ["init", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / ".consync.yaml").exists()

    def test_refuses_overwrite(self, runner, tmp_path):
        (tmp_path / ".consync.yaml").write_text("existing")
        result = runner.invoke(main, ["init", "--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "already exists" in result.output


class TestSyncCommand:
    def test_sync_creates_target(self, runner, project_dir):
        with runner.isolated_filesystem(temp_dir=project_dir):
            import os
            os.chdir(project_dir)
            result = runner.invoke(main, ["sync", "--config", str(project_dir / ".consync.yaml")])
            assert result.exit_code == 0
            assert (project_dir / "out.h").exists()

    def test_sync_dry_run(self, runner, project_dir):
        with runner.isolated_filesystem(temp_dir=project_dir):
            import os
            os.chdir(project_dir)
            result = runner.invoke(main, ["sync", "--config", str(project_dir / ".consync.yaml"), "--dry-run"])
            assert result.exit_code == 0
            assert not (project_dir / "out.h").exists()

    def test_sync_no_config(self, runner, tmp_path):
        import os
        os.chdir(tmp_path)
        result = runner.invoke(main, ["sync"])
        assert result.exit_code == 1
        assert "No .consync.yaml found" in result.output


class TestCheckCommand:
    def test_check_in_sync(self, runner, project_dir):
        import os
        os.chdir(project_dir)
        # First sync
        runner.invoke(main, ["sync", "--config", str(project_dir / ".consync.yaml")])
        # Then check
        result = runner.invoke(main, ["check", "--config", str(project_dir / ".consync.yaml")])
        assert result.exit_code == 0
        assert "in sync" in result.output.lower()

    def test_check_missing_target_fails(self, runner, project_dir):
        import os
        os.chdir(project_dir)
        result = runner.invoke(main, ["check", "--config", str(project_dir / ".consync.yaml")])
        assert result.exit_code == 1


class TestVersionCommand:
    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output
