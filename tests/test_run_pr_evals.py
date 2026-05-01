"""Tests for run-pr-evals.sh argument parsing and suite discovery."""
import json
import os
import stat
import subprocess

import pytest

SCRIPT = "plugins/skill-litmus/scripts/run-pr-evals.sh"


@pytest.fixture
def mock_tools(tmp_path):
    """Create mock scripts for claude, gh, and git diff output."""
    mock_dir = tmp_path / "mock-bin"
    mock_dir.mkdir()

    mock_claude = mock_dir / "claude"
    mock_claude.write_text(r'''#!/usr/bin/env bash
PROMPT="$2"
if echo "$PROMPT" | grep -q "Grade each assertion"; then
    EVAL_ID=$(echo "$PROMPT" | grep -oE "grading case [0-9]+" | grep -oE "[0-9]+")
    echo "{\"eval_id\": $EVAL_ID, \"assertions\": [{\"assertion\": \"test\", \"passed\": true, \"reasoning\": \"mock\"}]}"
else
    OUTPUTS_DIR=$(echo "$PROMPT" | grep -oE "/[^ ]*eval-[0-9]+/outputs/" | head -1)
    if [ -n "$OUTPUTS_DIR" ]; then
        mkdir -p "$OUTPUTS_DIR"
        echo "mock output" > "$OUTPUTS_DIR/result.txt"
    fi
    echo "executed"
fi
''')
    mock_claude.chmod(mock_claude.stat().st_mode | stat.S_IEXEC)
    return str(mock_dir)


def test_missing_required_args():
    result = subprocess.run(
        ["bash", SCRIPT],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "required" in result.stderr.lower()


def test_no_changed_suites_exits_cleanly(tmp_path, mock_tools):
    """When no suites match the changed files, exits 0 with message."""
    evals_dir = tmp_path / "evals" / "test-skill"
    evals_dir.mkdir(parents=True)
    (evals_dir / "evals.json").write_text(json.dumps({
        "skill_name": "test-skill",
        "plugin": "test-plugin",
        "evals": [{"id": 1, "prompt": "x", "expected_output": "y", "assertions": ["z"]}],
    }))

    workspace = tmp_path / "workspace"
    env = os.environ.copy()
    env["PATH"] = mock_tools + ":" + env["PATH"]
    result = subprocess.run(
        [
            "bash", SCRIPT,
            "--base-sha", "abc123",
            "--evals-dir", str(tmp_path / "evals") + "/",
            "--workspace-root", str(workspace),
            "--changed-files", "",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert "no changed suites" in result.stdout.lower()


def test_invalid_skill_name_skipped(tmp_path, mock_tools):
    """A suite with path-traversal skill_name is skipped."""
    evals_dir = tmp_path / "evals" / "legit-dir"
    evals_dir.mkdir(parents=True)
    (evals_dir / "evals.json").write_text(json.dumps({
        "skill_name": "../escaped",
        "plugin": "test-plugin",
        "evals": [{"id": 1, "prompt": "x", "expected_output": "y", "assertions": ["z"]}],
    }))

    workspace = tmp_path / "workspace"
    env = os.environ.copy()
    env["PATH"] = mock_tools + ":" + env["PATH"]

    # Provide changed-files that would match the directory
    result = subprocess.run(
        [
            "bash", SCRIPT,
            "--base-sha", "abc123",
            "--evals-dir", str(tmp_path / "evals") + "/",
            "--workspace-root", str(workspace),
            "--changed-files", str(evals_dir / "evals.json"),
        ],
        capture_output=True, text=True, env=env,
    )
    # Should not create a workspace at the traversal path
    assert not (tmp_path / "workspace" / ".." / "escaped").exists()
    assert "invalid skill_name" in result.stderr.lower()
