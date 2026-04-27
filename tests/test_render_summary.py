# tests/test_render_summary.py
import json
import subprocess
import sys


AGGREGATE_SCRIPT = "plugins/skill-litmus/scripts/aggregate_benchmark.py"
RENDER_SCRIPT = "plugins/skill-litmus/scripts/render_summary.py"


def setup_workspace_with_benchmark(workspace):
    """Populate workspace with sample results, then aggregate to produce benchmark.json."""
    workspace.add_eval(
        1,
        grading={
            "eval_id": 1,
            "assertions": [
                {"assertion": "Output exists", "passed": True, "reasoning": "Found"},
                {"assertion": "Format correct", "passed": True, "reasoning": "Valid"},
            ],
        },
        timing={"eval_id": 1, "duration_seconds": 30.0},
    )
    workspace.add_eval(
        2,
        grading={
            "eval_id": 2,
            "assertions": [
                {"assertion": "Contains header", "passed": True, "reasoning": "Yes"},
                {"assertion": "No errors", "passed": False, "reasoning": "Found error X"},
            ],
        },
        timing={"eval_id": 2, "duration_seconds": 20.0},
    )
    subprocess.run(
        [sys.executable, AGGREGATE_SCRIPT, "--results", str(workspace.root)],
        check=True,
    )


def run_render(workspace_path, baseline_path=None):
    cmd = [sys.executable, RENDER_SCRIPT, "--results", str(workspace_path)]
    if baseline_path:
        cmd += ["--baseline", str(baseline_path)]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_basic_rendering(workspace):
    setup_workspace_with_benchmark(workspace)

    result = run_render(workspace.root)
    assert result.returncode == 0

    summary = (workspace.root / "summary.md").read_text()
    assert "# Eval Results" in summary
    assert "1/2" in summary
    assert "3/4" in summary
    assert "eval-1" in summary
    assert "eval-2" in summary
    assert "PASS" in summary
    assert "FAIL" in summary


def test_failed_assertion_detail(workspace):
    setup_workspace_with_benchmark(workspace)

    result = run_render(workspace.root)
    assert result.returncode == 0

    summary = (workspace.root / "summary.md").read_text()
    assert "Failed Assertions" in summary
    assert "No errors" in summary
    assert "Found error X" in summary


def test_all_passing_no_failure_section(workspace):
    workspace.add_eval(
        1,
        grading={
            "eval_id": 1,
            "assertions": [
                {"assertion": "A", "passed": True, "reasoning": "ok"},
            ],
        },
        timing={"eval_id": 1, "duration_seconds": 10.0},
    )
    subprocess.run(
        [sys.executable, AGGREGATE_SCRIPT, "--results", str(workspace.root)],
        check=True,
    )

    result = run_render(workspace.root)
    assert result.returncode == 0

    summary = (workspace.root / "summary.md").read_text()
    assert "Failed Assertions" not in summary


def test_baseline_comparison(workspace, tmp_path):
    setup_workspace_with_benchmark(workspace)

    baseline = {
        "run_summary": {
            "total_evals": 2,
            "passed": 2,
            "failed": 0,
            "pass_rate": 1.0,
            "total_assertions": 4,
            "passed_assertions": 4,
            "failed_assertions": 0,
            "assertion_pass_rate": 1.0,
            "avg_duration_seconds": 30.0,
            "results": [],
        }
    }
    baseline_path = tmp_path / "baseline_benchmark.json"
    baseline_path.write_text(json.dumps(baseline))

    result = run_render(workspace.root, baseline_path)
    assert result.returncode == 0

    summary = (workspace.root / "summary.md").read_text()
    assert "Baseline" in summary
    assert "Pass rate" in summary
