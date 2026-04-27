import json
import subprocess
import sys


SCRIPT = "plugins/skill-litmus/scripts/aggregate_benchmark.py"


def run_aggregate(workspace_path):
    result = subprocess.run(
        [sys.executable, SCRIPT, "--results", str(workspace_path)],
        capture_output=True,
        text=True,
    )
    return result


def test_all_passing(workspace):
    workspace.add_eval(
        1,
        grading={
            "eval_id": 1,
            "assertions": [
                {"assertion": "Output exists", "passed": True, "reasoning": "Found"},
                {"assertion": "Format correct", "passed": True, "reasoning": "Valid"},
            ],
        },
        timing={"eval_id": 1, "duration_seconds": 30.5},
    )
    workspace.add_eval(
        2,
        grading={
            "eval_id": 2,
            "assertions": [
                {"assertion": "Contains header", "passed": True, "reasoning": "Yes"},
            ],
        },
        timing={"eval_id": 2, "duration_seconds": 20.0},
    )

    result = run_aggregate(workspace.root)
    assert result.returncode == 0

    benchmark = json.loads((workspace.root / "benchmark.json").read_text())
    s = benchmark["run_summary"]
    assert s["total_evals"] == 2
    assert s["passed"] == 2
    assert s["failed"] == 0
    assert s["pass_rate"] == 1.0
    assert s["total_assertions"] == 3
    assert s["passed_assertions"] == 3
    assert s["failed_assertions"] == 0
    assert s["assertion_pass_rate"] == 1.0
    assert s["avg_duration_seconds"] == 25.2
    assert len(s["results"]) == 2


def test_mixed_results(workspace):
    workspace.add_eval(
        1,
        grading={
            "eval_id": 1,
            "assertions": [
                {"assertion": "A", "passed": True, "reasoning": "ok"},
                {"assertion": "B", "passed": False, "reasoning": "missing"},
            ],
        },
        timing={"eval_id": 1, "duration_seconds": 40.0},
    )
    workspace.add_eval(
        2,
        grading={
            "eval_id": 2,
            "assertions": [
                {"assertion": "C", "passed": True, "reasoning": "ok"},
            ],
        },
        timing={"eval_id": 2, "duration_seconds": 20.0},
    )

    result = run_aggregate(workspace.root)
    assert result.returncode == 0

    benchmark = json.loads((workspace.root / "benchmark.json").read_text())
    s = benchmark["run_summary"]
    assert s["passed"] == 1
    assert s["failed"] == 1
    assert s["pass_rate"] == 0.5
    assert s["passed_assertions"] == 2
    assert s["failed_assertions"] == 1
    assert s["assertion_pass_rate"] == 0.667


def test_missing_timing(workspace):
    workspace.add_eval(
        1,
        grading={
            "eval_id": 1,
            "assertions": [
                {"assertion": "A", "passed": True, "reasoning": "ok"},
            ],
        },
    )

    result = run_aggregate(workspace.root)
    assert result.returncode == 0

    benchmark = json.loads((workspace.root / "benchmark.json").read_text())
    assert benchmark["run_summary"]["results"][0]["duration_seconds"] == 0.0


def test_empty_workspace(tmp_path):
    result = run_aggregate(tmp_path)
    assert result.returncode == 0

    benchmark = json.loads((tmp_path / "benchmark.json").read_text())
    s = benchmark["run_summary"]
    assert s["total_evals"] == 0
    assert s["pass_rate"] == 0.0
