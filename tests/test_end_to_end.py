"""End-to-end: evals.json -> run-evals.sh -> benchmark.json + summary.md."""
import json
import os
import stat
import subprocess

import pytest

RUN_EVALS = "plugins/skill-litmus/scripts/run-evals.sh"
SCHEMA = "evals.schema.json"


@pytest.fixture
def mock_claude_e2e(tmp_path):
    """Mock claude that writes deterministic output and grading."""
    mock_dir = tmp_path / "mock-bin"
    mock_dir.mkdir()
    mock_script = mock_dir / "claude"
    mock_script.write_text(r'''#!/usr/bin/env bash
PROMPT="$2"
if echo "$PROMPT" | grep -q "Grade each assertion"; then
    EVAL_ID=$(echo "$PROMPT" | grep -oE "case [0-9]+" | head -1 | grep -oE "[0-9]+")
    # Build a JSON response with one passing assertion per line starting with "- "
    ASSERTIONS="[]"
    ASSERTIONS=$(echo "$PROMPT" | grep "^- " | while IFS= read -r line; do
        text="${line#- }"
        echo "{\"assertion\": \"$text\", \"passed\": true, \"reasoning\": \"mock\"}"
    done | python3 -c "
import sys, json
items = []
for line in sys.stdin:
    line = line.strip()
    if line:
        items.append(json.loads(line))
if not items:
    items = [{\"assertion\": \"fallback\", \"passed\": True, \"reasoning\": \"mock\"}]
print(json.dumps({\"eval_id\": $EVAL_ID, \"assertions\": items}))
")
    echo "$ASSERTIONS"
else
    OUTPUTS_DIR=$(echo "$PROMPT" | grep -oE "/[^ ]*eval-[0-9]+/outputs/" | head -1)
    if [ -n "$OUTPUTS_DIR" ]; then
        mkdir -p "$OUTPUTS_DIR"
        echo "mock processed content" > "$OUTPUTS_DIR/result.txt"
    fi
    echo "executed"
fi
''')
    mock_script.chmod(mock_script.stat().st_mode | stat.S_IEXEC)
    return str(mock_dir)


@pytest.fixture
def full_eval_suite(tmp_path):
    """Create a complete suite with two cases."""
    suite_dir = tmp_path / "evals" / "demo-skill"
    suite_dir.mkdir(parents=True)
    files_dir = suite_dir / "files"
    files_dir.mkdir()
    (files_dir / "sample.md").write_text("# Sample\n\nTest content.")

    evals_json = {
        "skill_name": "demo-skill",
        "plugin": "demo-plugin",
        "evals": [
            {
                "id": 1,
                "prompt": "Process the sample file",
                "expected_output": "A transformed version of sample.md",
                "files": ["files/sample.md"],
                "assertions": [
                    "The output file exists",
                    "The output contains transformed content",
                ],
            },
            {
                "id": 2,
                "prompt": "Summarize the sample file",
                "expected_output": "A brief summary of the content",
                "files": ["files/sample.md"],
                "assertions": [
                    "The output contains a summary",
                ],
            },
        ],
    }
    (suite_dir / "evals.json").write_text(json.dumps(evals_json, indent=2))
    return suite_dir


def test_evals_json_validates_against_schema(full_eval_suite):
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = json.loads(open(SCHEMA).read())
    data = json.loads((full_eval_suite / "evals.json").read_text())
    jsonschema.validate(data, schema)


def test_full_pipeline(full_eval_suite, tmp_path, mock_claude_e2e):
    workspace = tmp_path / "workspace"
    env = os.environ.copy()
    env["PATH"] = mock_claude_e2e + ":" + env["PATH"]

    result = subprocess.run(
        [
            "bash", RUN_EVALS,
            "--evals", str(full_eval_suite / "evals.json"),
            "--skill", "demo-skill",
            "--workspace", str(workspace),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )

    # Workspace structure
    assert (workspace / "eval-1" / "outputs").is_dir()
    assert (workspace / "eval-2" / "outputs").is_dir()
    assert (workspace / "eval-1" / "timing.json").is_file()
    assert (workspace / "eval-2" / "timing.json").is_file()
    assert (workspace / "eval-1" / "grading.json").is_file()
    assert (workspace / "eval-2" / "grading.json").is_file()

    # Aggregated outputs
    assert (workspace / "benchmark.json").is_file()
    assert (workspace / "summary.md").is_file()

    # benchmark.json structure
    benchmark = json.loads((workspace / "benchmark.json").read_text())
    assert "run_summary" in benchmark
    s = benchmark["run_summary"]
    assert s["total_evals"] == 2
    assert len(s["results"]) == 2

    # summary.md contains expected sections
    summary = (workspace / "summary.md").read_text()
    assert "Eval Results" in summary
    assert "eval-1" in summary
    assert "eval-2" in summary

    # timing.json has duration
    timing = json.loads((workspace / "eval-1" / "timing.json").read_text())
    assert "duration_seconds" in timing
    assert timing["duration_seconds"] >= 0
