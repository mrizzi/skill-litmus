"""Integration tests for run-evals.sh using a mock claude CLI."""
import json
import os
import stat
import subprocess

import pytest

RUN_EVALS = "plugins/skill-litmus/scripts/run-evals.sh"


@pytest.fixture
def mock_claude(tmp_path):
    """Create a mock 'claude' script that writes deterministic outputs
    and returns grading JSON when given a grading prompt."""
    mock_dir = tmp_path / "mock-bin"
    mock_dir.mkdir()
    mock_script = mock_dir / "claude"
    # The mock inspects $2 (the prompt after -p) to decide behavior.
    # Grading prompt contains "Grade each assertion" -- respond with JSON.
    # Execution prompt contains "eval-<id>/outputs/" -- write a file there.
    mock_script.write_text(r'''#!/usr/bin/env bash
PROMPT="$2"
if echo "$PROMPT" | grep -q "Grade each assertion"; then
    EVAL_ID=$(echo "$PROMPT" | grep -oE "grading case [0-9]+" | grep -oE "[0-9]+")
    echo "{\"eval_id\": $EVAL_ID, \"assertions\": [{\"assertion\": \"test\", \"passed\": true, \"reasoning\": \"mock pass\"}]}"
else
    OUTPUTS_DIR=$(echo "$PROMPT" | grep -oE "/[^ ]*eval-[0-9]+/outputs/" | head -1)
    if [ -n "$OUTPUTS_DIR" ]; then
        mkdir -p "$OUTPUTS_DIR"
        echo "mock output" > "$OUTPUTS_DIR/result.txt"
    fi
    echo "executed"
fi
''')
    mock_script.chmod(mock_script.stat().st_mode | stat.S_IEXEC)
    return str(mock_dir)


@pytest.fixture
def simple_eval_suite(tmp_path):
    """Create a minimal suite with one case."""
    suite_dir = tmp_path / "evals" / "test-skill"
    suite_dir.mkdir(parents=True)
    files_dir = suite_dir / "files"
    files_dir.mkdir()
    (files_dir / "input.txt").write_text("sample fixture content")

    evals_json = {
        "skill_name": "test-skill",
        "plugin": "test-plugin",
        "evals": [
            {
                "id": 1,
                "prompt": "Run the test skill on input.txt",
                "expected_output": "A processed output file",
                "files": ["files/input.txt"],
                "assertions": ["The output contains processed content"],
            }
        ],
    }
    (suite_dir / "evals.json").write_text(json.dumps(evals_json, indent=2))
    return suite_dir


def test_missing_required_args(tmp_path):
    result = subprocess.run(
        ["bash", RUN_EVALS, "--evals", "/nonexistent"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "required" in result.stderr.lower()


def test_workspace_layout_created(simple_eval_suite, tmp_path, mock_claude):
    workspace = tmp_path / "workspace"
    env = os.environ.copy()
    env["PATH"] = mock_claude + ":" + env["PATH"]

    subprocess.run(
        [
            "bash", RUN_EVALS,
            "--evals", str(simple_eval_suite / "evals.json"),
            "--skill", "test-skill",
            "--workspace", str(workspace),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )

    assert (workspace / "eval-1").is_dir()
    assert (workspace / "eval-1" / "outputs").is_dir()
    assert (workspace / "eval-1" / "timing.json").is_file()
    assert (workspace / "eval-1" / "grading.json").is_file()
    assert (workspace / "benchmark.json").is_file()
    assert (workspace / "summary.md").is_file()


def test_plugin_auto_detect_from_evals_json(simple_eval_suite, tmp_path, mock_claude):
    workspace = tmp_path / "workspace"
    env = os.environ.copy()
    env["PATH"] = mock_claude + ":" + env["PATH"]

    result = subprocess.run(
        [
            "bash", RUN_EVALS,
            "--evals", str(simple_eval_suite / "evals.json"),
            "--skill", "test-skill",
            "--workspace", str(workspace),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert result.returncode == 0
