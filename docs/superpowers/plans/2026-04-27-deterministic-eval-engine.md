# Deterministic Eval Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 4 deterministic scripts and the GitHub Action that compose the skill-litmus engine.

**Architecture:** Shell orchestrator (`run-evals.sh`) invokes `claude -p` for eval-case execution and grading, then calls two Python scripts for aggregation and rendering. A fourth shell script handles CI posting. A composite GitHub Action ties them together with event-driven behavior.

**Tech Stack:** Bash (requires `jq`), Python 3 (stdlib only), `claude` CLI, `gh` CLI (CI only), pytest (dev only)

---

## File Map

| File | Responsibility | Status |
|------|---------------|--------|
| `plugins/skill-litmus/scripts/aggregate_benchmark.py` | Read `eval-*/grading.json` + `eval-*/timing.json`, write `benchmark.json` | Stub |
| `plugins/skill-litmus/scripts/render_summary.py` | Read `benchmark.json` + optional baseline, write `summary.md` | Stub |
| `plugins/skill-litmus/scripts/run-evals.sh` | Parse `evals.json`, create workspace, invoke `claude -p` for execution + grading, call Python scripts | Stub |
| `plugins/skill-litmus/scripts/post-results.sh` | PR comment via `gh` CLI or baseline commit via `git` | Stub |
| `action.yml` | Composite GitHub Action -- detect event, discover skills, call scripts | Placeholder |
| `tests/conftest.py` | Shared pytest fixtures (workspace builders) | New |
| `tests/test_aggregate_benchmark.py` | Unit tests for aggregation | New |
| `tests/test_render_summary.py` | Unit tests for rendering | New |
| `tests/test_run_evals.py` | Integration tests for orchestrator (mocked `claude`) | New |
| `tests/test_end_to_end.py` | Full pipeline test | New |

---

### Task 1: aggregate_benchmark.py

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_aggregate_benchmark.py`
- Modify: `plugins/skill-litmus/scripts/aggregate_benchmark.py`

- [ ] **Step 1: Create shared test fixtures**

```python
# tests/conftest.py
import json
import pytest


@pytest.fixture
def workspace(tmp_path):
    """Create a workspace directory and return a builder for populating it."""

    class WorkspaceBuilder:
        def __init__(self, root):
            self.root = root

        def add_eval(self, eval_id, grading, timing=None):
            eval_dir = self.root / f"eval-{eval_id}"
            eval_dir.mkdir(parents=True, exist_ok=True)
            (eval_dir / "grading.json").write_text(json.dumps(grading))
            if timing is not None:
                (eval_dir / "timing.json").write_text(json.dumps(timing))
            return eval_dir

        def add_outputs(self, eval_id, files):
            outputs_dir = self.root / f"eval-{eval_id}" / "outputs"
            outputs_dir.mkdir(parents=True, exist_ok=True)
            for name, content in files.items():
                (outputs_dir / name).write_text(content)
            return outputs_dir

    return WorkspaceBuilder(tmp_path)
```

- [ ] **Step 2: Write failing tests for aggregate_benchmark.py**

```python
# tests/test_aggregate_benchmark.py
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
```

- [ ] **Step 3: Run tests -- verify they fail**

Run: `cd /Users/mrizzi/git/cloned/skill-litmus && python3 -m pytest tests/test_aggregate_benchmark.py -v`
Expected: 4 FAILED (script exits with "not yet implemented")

- [ ] **Step 4: Implement aggregate_benchmark.py**

Replace the full contents of `plugins/skill-litmus/scripts/aggregate_benchmark.py`:

```python
#!/usr/bin/env python3
"""Aggregate grading and timing results into benchmark.json."""

import argparse
import glob
import json
import os
import sys


def load_json(path):
    with open(path) as f:
        return json.load(f)


def aggregate(results_dir):
    eval_dirs = sorted(
        glob.glob(os.path.join(results_dir, "eval-*")),
        key=lambda d: int(os.path.basename(d).split("-", 1)[1]),
    )

    results = []
    total_assertions = 0
    passed_assertions = 0
    total_duration = 0.0

    for eval_dir in eval_dirs:
        grading_path = os.path.join(eval_dir, "grading.json")
        timing_path = os.path.join(eval_dir, "timing.json")

        if not os.path.exists(grading_path):
            print(f"Warning: {grading_path} not found, skipping", file=sys.stderr)
            continue

        grading = load_json(grading_path)
        eval_id = grading["eval_id"]
        assertions = grading["assertions"]
        n_passed = sum(1 for a in assertions if a["passed"])
        n_total = len(assertions)

        total_assertions += n_total
        passed_assertions += n_passed

        duration = 0.0
        if os.path.exists(timing_path):
            timing = load_json(timing_path)
            duration = timing.get("duration_seconds", 0.0)
        total_duration += duration

        results.append({
            "eval_id": eval_id,
            "passed": n_passed == n_total,
            "assertions_passed": n_passed,
            "assertions_total": n_total,
            "duration_seconds": duration,
        })

    n_evals = len(results)
    n_passed_evals = sum(1 for r in results if r["passed"])

    benchmark = {
        "run_summary": {
            "total_evals": n_evals,
            "passed": n_passed_evals,
            "failed": n_evals - n_passed_evals,
            "pass_rate": round(n_passed_evals / n_evals, 3) if n_evals else 0.0,
            "total_assertions": total_assertions,
            "passed_assertions": passed_assertions,
            "failed_assertions": total_assertions - passed_assertions,
            "assertion_pass_rate": round(passed_assertions / total_assertions, 3) if total_assertions else 0.0,
            "avg_duration_seconds": round(total_duration / n_evals, 1) if n_evals else 0.0,
            "results": results,
        }
    }

    output_path = os.path.join(results_dir, "benchmark.json")
    with open(output_path, "w") as f:
        json.dump(benchmark, f, indent=2)
        f.write("\n")

    return benchmark


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate results into benchmark.json"
    )
    parser.add_argument(
        "--results", required=True, help="Workspace directory containing eval-* subdirs"
    )
    args = parser.parse_args()

    if not os.path.isdir(args.results):
        print(f"Error: {args.results} is not a directory", file=sys.stderr)
        sys.exit(1)

    benchmark = aggregate(args.results)
    summary = benchmark["run_summary"]
    print(
        f"Aggregated {summary['total_evals']} evals: "
        f"{summary['passed']} passed, {summary['failed']} failed"
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests -- verify they pass**

Run: `cd /Users/mrizzi/git/cloned/skill-litmus && python3 -m pytest tests/test_aggregate_benchmark.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_aggregate_benchmark.py plugins/skill-litmus/scripts/aggregate_benchmark.py
git commit -m "feat: implement aggregate_benchmark.py with tests"
```

---

### Task 2: render_summary.py

**Files:**
- Create: `tests/test_render_summary.py`
- Modify: `plugins/skill-litmus/scripts/render_summary.py`

- [ ] **Step 1: Write failing tests**

```python
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
```

- [ ] **Step 2: Run tests -- verify they fail**

Run: `cd /Users/mrizzi/git/cloned/skill-litmus && python3 -m pytest tests/test_render_summary.py -v`
Expected: 4 FAILED (script exits with "not yet implemented")

- [ ] **Step 3: Implement render_summary.py**

Replace the full contents of `plugins/skill-litmus/scripts/render_summary.py`:

```python
#!/usr/bin/env python3
"""Render results as Markdown summary with optional baseline comparison."""

import argparse
import json
import os
import sys


def load_json(path):
    with open(path) as f:
        return json.load(f)


def fmt_pct(value):
    return f"{value:.1%}"


def fmt_delta(value, fmt_fn=fmt_pct, invert=False):
    sign = "+" if value >= 0 else ""
    indicator = ""
    if value > 0:
        indicator = " (worse)" if invert else " (better)"
    elif value < 0:
        indicator = " (better)" if invert else " (worse)"
    return f"{sign}{fmt_fn(value)}{indicator}"


def render(results_dir, baseline_path=None):
    benchmark_path = os.path.join(results_dir, "benchmark.json")
    if not os.path.exists(benchmark_path):
        print(f"Error: {benchmark_path} not found", file=sys.stderr)
        sys.exit(1)

    benchmark = load_json(benchmark_path)
    s = benchmark["run_summary"]

    baseline = None
    if baseline_path and os.path.exists(baseline_path):
        baseline = load_json(baseline_path)

    lines = []
    lines.append("# Eval Results")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(
        f"| Evals passed | {s['passed']}/{s['total_evals']}"
        f" ({fmt_pct(s['pass_rate'])}) |"
    )
    lines.append(
        f"| Assertions passed | {s['passed_assertions']}/{s['total_assertions']}"
        f" ({fmt_pct(s['assertion_pass_rate'])}) |"
    )
    lines.append(f"| Avg duration | {s['avg_duration_seconds']:.1f}s |")

    if baseline:
        bs = baseline["run_summary"]
        delta_pass = s["pass_rate"] - bs["pass_rate"]
        delta_assert = s["assertion_pass_rate"] - bs["assertion_pass_rate"]
        delta_dur = s["avg_duration_seconds"] - bs["avg_duration_seconds"]

        lines.append("")
        lines.append("### vs. Baseline")
        lines.append("")
        lines.append("| Metric | Delta |")
        lines.append("|--------|-------|")
        lines.append(f"| Pass rate | {fmt_delta(delta_pass)} |")
        lines.append(f"| Assertion pass rate | {fmt_delta(delta_assert)} |")
        lines.append(
            f"| Avg duration | "
            f"{fmt_delta(delta_dur, lambda v: f'{v:.1f}s', invert=True)} |"
        )

    lines.append("")
    lines.append("## Per-Eval Results")
    lines.append("")
    lines.append("| Eval | Status | Assertions | Duration |")
    lines.append("|------|--------|------------|----------|")

    for result in s["results"]:
        status = "PASS" if result["passed"] else "FAIL"
        lines.append(
            f"| eval-{result['eval_id']} | {status} "
            f"| {result['assertions_passed']}/{result['assertions_total']} "
            f"| {result['duration_seconds']:.1f}s |"
        )

    failed_results = [r for r in s["results"] if not r["passed"]]
    if failed_results:
        lines.append("")
        lines.append("## Failed Assertions")
        lines.append("")
        for result in failed_results:
            eval_id = result["eval_id"]
            grading_path = os.path.join(
                results_dir, f"eval-{eval_id}", "grading.json"
            )
            if os.path.exists(grading_path):
                grading = load_json(grading_path)
                lines.append(f"### eval-{eval_id}")
                lines.append("")
                for assertion in grading["assertions"]:
                    if not assertion["passed"]:
                        lines.append(f"- **{assertion['assertion']}**")
                        lines.append(f"  - {assertion['reasoning']}")
                lines.append("")

    output = "\n".join(lines)
    if not output.endswith("\n"):
        output += "\n"

    output_path = os.path.join(results_dir, "summary.md")
    with open(output_path, "w") as f:
        f.write(output)

    return output


def main():
    parser = argparse.ArgumentParser(
        description="Render summary as Markdown"
    )
    parser.add_argument("--results", required=True, help="Workspace directory")
    parser.add_argument(
        "--baseline", help="Path to baseline benchmark.json for comparison"
    )
    args = parser.parse_args()

    if not os.path.isdir(args.results):
        print(f"Error: {args.results} is not a directory", file=sys.stderr)
        sys.exit(1)

    render(args.results, args.baseline)
    print(f"Summary written to {os.path.join(args.results, 'summary.md')}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests -- verify they pass**

Run: `cd /Users/mrizzi/git/cloned/skill-litmus && python3 -m pytest tests/test_render_summary.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_render_summary.py plugins/skill-litmus/scripts/render_summary.py
git commit -m "feat: implement render_summary.py with tests"
```

---

### Task 3: run-evals.sh

The core orchestrator. Parses `evals.json`, creates workspace layout, invokes `claude -p` for execution and grading, captures timing, then calls the Python scripts.

**Files:**
- Modify: `plugins/skill-litmus/scripts/run-evals.sh`
- Create: `tests/test_run_evals.py`

- [ ] **Step 1: Implement run-evals.sh**

Replace the full contents of `plugins/skill-litmus/scripts/run-evals.sh`:

```bash
#!/usr/bin/env bash
# Deterministic orchestrator.
# See docs/specs/2026-04-24-standalone-eval-runner-design.md Section 2.
#
# Usage:
#   run-evals.sh --evals <path> --skill <name> --workspace <dir> \
#                [--plugin <namespace>] [--baseline <path>]

set -euo pipefail

EVALS_PATH=""
SKILL_NAME=""
WORKSPACE=""
PLUGIN=""
BASELINE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --evals)     EVALS_PATH="$2";  shift 2 ;;
        --skill)     SKILL_NAME="$2";  shift 2 ;;
        --workspace) WORKSPACE="$2";   shift 2 ;;
        --plugin)    PLUGIN="$2";      shift 2 ;;
        --baseline)  BASELINE="$2";    shift 2 ;;
        *) echo "Error: unknown argument: $1" >&2; exit 1 ;;
    esac
done

[[ -z "$EVALS_PATH" ]] && echo "Error: --evals required" >&2 && exit 1
[[ -z "$SKILL_NAME" ]] && echo "Error: --skill required" >&2 && exit 1
[[ -z "$WORKSPACE" ]]  && echo "Error: --workspace required" >&2 && exit 1

# Resolve evals.json path
if [[ -d "$EVALS_PATH" ]]; then
    EVALS_FILE="$EVALS_PATH/evals.json"
else
    EVALS_FILE="$EVALS_PATH"
fi
[[ ! -f "$EVALS_FILE" ]] && echo "Error: $EVALS_FILE not found" >&2 && exit 1
EVALS_DIR="$(cd "$(dirname "$EVALS_FILE")" && pwd)"
EVALS_FILE="$EVALS_DIR/$(basename "$EVALS_FILE")"

# Auto-detect plugin namespace
if [[ -z "$PLUGIN" ]]; then
    PLUGIN=$(jq -r '.plugin // empty' "$EVALS_FILE")
fi
if [[ -z "$PLUGIN" ]]; then
    search_dir="$EVALS_DIR"
    while [[ "$search_dir" != "/" ]]; do
        if [[ -f "$search_dir/.claude-plugin/plugin.json" ]]; then
            PLUGIN=$(jq -r '.name' "$search_dir/.claude-plugin/plugin.json")
            break
        fi
        search_dir="$(dirname "$search_dir")"
    done
fi
if [[ -z "$PLUGIN" ]]; then
    echo "Error: could not detect plugin namespace. Use --plugin." >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_CMD="/$PLUGIN:$SKILL_NAME"

# Parse IDs
EVAL_IDS=$(jq -r '.evals[].id' "$EVALS_FILE")
if [[ -z "$EVAL_IDS" ]]; then
    echo "Error: no cases found in $EVALS_FILE" >&2
    exit 1
fi

# Create workspace layout
mkdir -p "$WORKSPACE"
for id in $EVAL_IDS; do
    mkdir -p "$WORKSPACE/eval-$id/outputs"
done

NUM_EVALS=$(echo "$EVAL_IDS" | wc -w | tr -d ' ')
echo "Running $NUM_EVALS cases for skill $SKILL_CMD"

# --- Execute cases in parallel ---
pids=()
for id in $EVAL_IDS; do
    (
        case_json=$(jq ".evals[] | select(.id == $id)" "$EVALS_FILE")
        prompt=$(echo "$case_json" | jq -r '.prompt')
        expected=$(echo "$case_json" | jq -r '.expected_output')
        files_json=$(echo "$case_json" | jq -r '.files // []')

        # Build the execution prompt
        exec_prompt="You are running case $id for the skill $SKILL_CMD.

User prompt for the skill:
$prompt

Expected output:
$expected"

        # Append fixture file contents
        file_count=$(echo "$files_json" | jq -r 'length')
        for (( i=0; i<file_count; i++ )); do
            rel_path=$(echo "$files_json" | jq -r ".[$i]")
            abs_path="$EVALS_DIR/$rel_path"
            if [[ -f "$abs_path" ]]; then
                exec_prompt="$exec_prompt

--- Fixture: $rel_path ---
$(cat "$abs_path")"
            else
                echo "Warning: fixture $abs_path not found" >&2
            fi
        done

        exec_prompt="$exec_prompt

Instructions:
1. Copy any fixture files above into the current working directory.
2. Invoke the skill $SKILL_CMD with the user prompt shown above.
3. Save all skill outputs into: $WORKSPACE/eval-$id/outputs/
4. Do not grade or assess the output. Just execute and capture."

        # Capture wall-clock timing via Python (portable across macOS and Linux)
        start=$(python3 -c "import time; print(time.time())")

        claude -p "$exec_prompt" \
            --permission-mode dontAsk \
            --allowedTools "Read,Write,Bash,Skill,Agent,Glob,Edit" \
            > "$WORKSPACE/eval-$id/execution.log" 2>&1 || true

        end=$(python3 -c "import time; print(time.time())")
        duration=$(python3 -c "print(round($end - $start, 1))")

        cat > "$WORKSPACE/eval-$id/timing.json" <<TIMING_EOF
{
  "eval_id": $id,
  "duration_seconds": $duration
}
TIMING_EOF

        echo "  eval-$id executed (${duration}s)"
    ) &
    pids+=($!)
done

for pid in "${pids[@]}"; do
    wait "$pid" || true
done

# --- Grade cases in parallel ---
echo "Grading..."
pids=()
for id in $EVAL_IDS; do
    (
        case_json=$(jq ".evals[] | select(.id == $id)" "$EVALS_FILE")
        expected=$(echo "$case_json" | jq -r '.expected_output')

        # Build assertion list
        assertion_list=""
        while IFS= read -r line; do
            assertion_list="$assertion_list
- $line"
        done < <(echo "$case_json" | jq -r '.assertions[]')

        # Collect output file contents
        output_contents=""
        if [[ -d "$WORKSPACE/eval-$id/outputs" ]]; then
            while IFS= read -r f; do
                [[ -z "$f" ]] && continue
                output_contents="$output_contents

--- $(basename "$f") ---
$(cat "$f")"
            done < <(find "$WORKSPACE/eval-$id/outputs" -type f 2>/dev/null)
        fi

        if [[ -z "$output_contents" ]]; then
            output_contents="(no output files found)"
        fi

        grading_prompt="You are grading case $id. Grade each assertion as passed or failed based on the actual outputs.

Expected output description:
$expected

Assertions to grade:
$assertion_list

Actual outputs:
$output_contents

Respond with ONLY valid JSON in this exact format (no markdown fences, no extra text):
{
  \"eval_id\": $id,
  \"assertions\": [
    {\"assertion\": \"<text>\", \"passed\": true, \"reasoning\": \"<brief>\"}
  ]
}

Grade each assertion independently. Be strict."

        claude -p "$grading_prompt" \
            --permission-mode dontAsk \
            --allowedTools "Read,Bash,Glob" \
            > "$WORKSPACE/eval-$id/grading_raw.txt" 2>&1 || true

        # Extract JSON from grading response
        python3 - "$WORKSPACE/eval-$id" "$id" <<'PYEOF'
import json, re, sys

eval_dir = sys.argv[1]
eval_id = int(sys.argv[2])
raw_path = f"{eval_dir}/grading_raw.txt"
out_path = f"{eval_dir}/grading.json"

try:
    text = open(raw_path).read()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        data = json.loads(match.group())
        data["eval_id"] = eval_id
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
    else:
        raise ValueError("No JSON object found in grading response")
except Exception as e:
    fallback = {
        "eval_id": eval_id,
        "assertions": [],
        "error": str(e),
    }
    with open(out_path, "w") as f:
        json.dump(fallback, f, indent=2)
        f.write("\n")
    print(f"Warning: grading parse failed for eval-{eval_id}: {e}", file=sys.stderr)
PYEOF

        echo "  eval-$id graded"
    ) &
    pids+=($!)
done

for pid in "${pids[@]}"; do
    wait "$pid" || true
done

# --- Create empty feedback.json ---
echo '{}' > "$WORKSPACE/feedback.json"

# --- Aggregate ---
echo "Aggregating results..."
python3 "$SCRIPT_DIR/aggregate_benchmark.py" --results "$WORKSPACE"

# --- Render summary ---
baseline_arg=""
if [[ -n "$BASELINE" ]]; then
    baseline_arg="--baseline $BASELINE"
fi
# shellcheck disable=SC2086
python3 "$SCRIPT_DIR/render_summary.py" --results "$WORKSPACE" $baseline_arg

echo ""
echo "Run complete. Results: $WORKSPACE/summary.md"
```

- [ ] **Step 2: Write integration tests with mocked claude**

```python
# tests/test_run_evals.py
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
    assert (workspace / "feedback.json").is_file()


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
```

- [ ] **Step 3: Run tests -- verify they pass**

Run: `cd /Users/mrizzi/git/cloned/skill-litmus && python3 -m pytest tests/test_run_evals.py -v --timeout=120`
Expected: 3 passed

- [ ] **Step 4: Commit**

```bash
git add plugins/skill-litmus/scripts/run-evals.sh tests/test_run_evals.py
git commit -m "feat: implement run-evals.sh with integration tests"
```

---

### Task 4: post-results.sh

Two modes: `pr` (post/update PR comment via `gh`) and `baseline` (commit baseline results via `git`).

**Files:**
- Modify: `plugins/skill-litmus/scripts/post-results.sh`

- [ ] **Step 1: Implement post-results.sh**

Replace the full contents of `plugins/skill-litmus/scripts/post-results.sh`:

```bash
#!/usr/bin/env bash
# Post results: PR comment or baseline commit.
# See docs/specs/2026-04-24-standalone-eval-runner-design.md Section 3.
#
# Usage:
#   post-results.sh pr       --workspace <dir> [--workspace <dir> ...]
#   post-results.sh baseline --workspace <dir> --evals-dir <path> --commit-hash <hash>

set -euo pipefail

COMMENT_MARKER="<!-- skill-litmus-results -->"

MODE="${1:-}"
[[ -z "$MODE" ]] && echo "Usage: post-results.sh {pr|baseline} [options]" >&2 && exit 1
shift

case "$MODE" in
    pr)
        WORKSPACES=()
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --workspace) WORKSPACES+=("$2"); shift 2 ;;
                *) echo "Error: unknown argument: $1" >&2; exit 1 ;;
            esac
        done

        [[ ${#WORKSPACES[@]} -eq 0 ]] && echo "Error: at least one --workspace required" >&2 && exit 1

        # Build combined comment body
        BODY="$COMMENT_MARKER"$'\n'"## Skill Eval Results"$'\n'
        for ws in "${WORKSPACES[@]}"; do
            if [[ -f "$ws/summary.md" ]]; then
                BODY+=$'\n'"$(cat "$ws/summary.md")"$'\n'$'\n'"---"$'\n'
            else
                BODY+=$'\n'"**Warning:** No summary found in $ws"$'\n'
            fi
        done

        # Detect PR number
        PR_NUMBER=$(gh pr view --json number -q '.number' 2>/dev/null || true)
        if [[ -z "$PR_NUMBER" ]]; then
            echo "Error: could not detect PR number. Are you in a PR context?" >&2
            exit 1
        fi

        # Find existing skill-litmus comment to update
        COMMENT_ID=$(gh api "repos/{owner}/{repo}/issues/$PR_NUMBER/comments" \
            --jq ".[] | select(.body | startswith(\"$COMMENT_MARKER\")) | .id" \
            2>/dev/null | head -1 || true)

        if [[ -n "$COMMENT_ID" ]]; then
            gh api "repos/{owner}/{repo}/issues/comments/$COMMENT_ID" \
                -X PATCH -f body="$BODY" > /dev/null
            echo "Updated existing PR comment ($COMMENT_ID)"
        else
            gh pr comment "$PR_NUMBER" --body "$BODY" > /dev/null
            echo "Posted new PR comment"
        fi
        ;;

    baseline)
        WORKSPACE=""
        EVALS_DIR=""
        COMMIT_HASH=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --workspace)   WORKSPACE="$2";   shift 2 ;;
                --evals-dir)   EVALS_DIR="$2";   shift 2 ;;
                --commit-hash) COMMIT_HASH="$2"; shift 2 ;;
                *) echo "Error: unknown argument: $1" >&2; exit 1 ;;
            esac
        done

        [[ -z "$WORKSPACE" ]]   && echo "Error: --workspace required" >&2 && exit 1
        [[ -z "$EVALS_DIR" ]]   && echo "Error: --evals-dir required" >&2 && exit 1
        [[ -z "$COMMIT_HASH" ]] && echo "Error: --commit-hash required" >&2 && exit 1

        BASELINE_DIR="$EVALS_DIR/baselines/$COMMIT_HASH"
        mkdir -p "$BASELINE_DIR"

        cp "$WORKSPACE/benchmark.json" "$BASELINE_DIR/"

        # Relative symlink so it works when the repo is cloned anywhere
        ln -snf "$COMMIT_HASH" "$EVALS_DIR/baselines/latest"

        git add "$EVALS_DIR/baselines/"
        git commit -m "chore: update baseline for ${COMMIT_HASH:0:7}" || true
        git push || true

        echo "Baseline committed: $BASELINE_DIR"
        ;;

    *)
        echo "Usage: post-results.sh {pr|baseline} [options]" >&2
        exit 1
        ;;
esac
```

- [ ] **Step 2: Verify syntax**

Run: `cd /Users/mrizzi/git/cloned/skill-litmus && bash -n plugins/skill-litmus/scripts/post-results.sh && echo "Syntax OK"`
Expected: "Syntax OK"

Run: `bash plugins/skill-litmus/scripts/post-results.sh 2>&1; echo "exit: $?"`
Expected: stderr contains "Usage:", exit code 1

- [ ] **Step 3: Commit**

```bash
git add plugins/skill-litmus/scripts/post-results.sh
git commit -m "feat: implement post-results.sh for PR comments and baselines"
```

---

### Task 5: action.yml

Composite GitHub Action that detects event type, discovers changed skills, calls `run-evals.sh` and `post-results.sh`.

**Files:**
- Modify: `action.yml`

- [ ] **Step 1: Implement action.yml**

Replace the full contents of `action.yml`:

```yaml
name: 'Skill Litmus'
description: 'Run eval suites for Claude Code skills and report results'

inputs:
  evals-dir:
    description: 'Path to evals directory'
    required: false
    default: 'evals/'
  skills-dir:
    description: 'Path to skills directory (auto-detected from plugin.json if omitted)'
    required: false
  baseline-branch:
    description: 'Branch for baseline comparison (defaults to repo default branch)'
    required: false

runs:
  using: 'composite'
  steps:
    - name: Verify dependencies
      shell: bash
      run: |
        for cmd in jq python3 claude; do
          if ! command -v "$cmd" &>/dev/null; then
            echo "::error::$cmd is required but not found"
            exit 1
          fi
        done

    - name: Run evals
      shell: bash
      env:
        EVALS_DIR: ${{ inputs.evals-dir }}
        SKILLS_DIR: ${{ inputs.skills-dir }}
        BASELINE_BRANCH: ${{ inputs.baseline-branch }}
      run: |
        SCRIPT_DIR="${{ github.action_path }}/plugins/skill-litmus/scripts"
        WORKSPACE_ROOT=$(mktemp -d)
        EVENT="$GITHUB_EVENT_NAME"

        # Resolve baseline branch
        if [[ -z "${BASELINE_BRANCH:-}" ]]; then
          BASELINE_BRANCH=$(gh repo view --json defaultBranchRef -q '.defaultBranchRef.name' 2>/dev/null || echo "main")
        fi

        if [[ "$EVENT" == "pull_request" ]]; then
          # --- PR mode: run only changed skills ---
          BASE_SHA="${{ github.event.pull_request.base.sha }}"
          CHANGED=$(git diff --name-only "$BASE_SHA"...HEAD)

          # Discover suites whose skill or evals.json changed
          EVALS_TO_RUN=()
          for evals_json in ${EVALS_DIR}*/evals.json; do
            [[ ! -f "$evals_json" ]] && continue
            skill_dir="$(dirname "$evals_json")"
            skill_name="$(basename "$skill_dir")"

            if echo "$CHANGED" | grep -qE "(${skill_dir}/|${SKILLS_DIR:-skills/}.*${skill_name})"; then
              EVALS_TO_RUN+=("$evals_json")
            fi
          done

          if [[ ${#EVALS_TO_RUN[@]} -eq 0 ]]; then
            echo "No changed suites detected."
            exit 0
          fi

          WORKSPACE_ARGS=()
          for evals_json in "${EVALS_TO_RUN[@]}"; do
            skill_name=$(jq -r '.skill_name' "$evals_json")
            ws="$WORKSPACE_ROOT/$skill_name"
            skill_dir="$(dirname "$evals_json")"

            # Try to fetch baseline from the base branch
            baseline_arg=""
            baseline_file="$skill_dir/baselines/latest/benchmark.json"
            baseline_tmp="$WORKSPACE_ROOT/baseline-${skill_name}.json"
            if git show "$BASELINE_BRANCH:$baseline_file" > "$baseline_tmp" 2>/dev/null; then
              baseline_arg="--baseline $baseline_tmp"
            fi

            # shellcheck disable=SC2086
            bash "$SCRIPT_DIR/run-evals.sh" \
              --evals "$evals_json" \
              --skill "$skill_name" \
              --workspace "$ws" \
              $baseline_arg

            WORKSPACE_ARGS+=("--workspace" "$ws")
          done

          if [[ ${#WORKSPACE_ARGS[@]} -gt 0 ]]; then
            bash "$SCRIPT_DIR/post-results.sh" pr "${WORKSPACE_ARGS[@]}"
          fi

        elif [[ "$EVENT" == "push" ]]; then
          # --- Push mode: run all suites, commit baselines ---
          for evals_json in ${EVALS_DIR}*/evals.json; do
            [[ ! -f "$evals_json" ]] && continue
            skill_name=$(jq -r '.skill_name' "$evals_json")
            skill_dir="$(dirname "$evals_json")"
            ws="$WORKSPACE_ROOT/$skill_name"

            bash "$SCRIPT_DIR/run-evals.sh" \
              --evals "$evals_json" \
              --skill "$skill_name" \
              --workspace "$ws"

            bash "$SCRIPT_DIR/post-results.sh" baseline \
              --workspace "$ws" \
              --evals-dir "$skill_dir" \
              --commit-hash "$GITHUB_SHA"
          done

        else
          echo "Unsupported event: $EVENT -- skipping."
          exit 0
        fi
```

- [ ] **Step 2: Validate YAML syntax**

Run: `cd /Users/mrizzi/git/cloned/skill-litmus && python3 -c "import yaml; yaml.safe_load(open('action.yml')); print('Valid YAML')" 2>/dev/null || python3 -c "print('PyYAML not installed -- manually inspect action.yml')"`

If PyYAML is unavailable, visually verify the YAML indentation is consistent (2-space indent under each key).

- [ ] **Step 3: Commit**

```bash
git add action.yml
git commit -m "feat: implement GitHub Action with event-driven behavior"
```

---

### Task 6: End-to-end validation

Verify all scripts work together with a self-contained dummy suite. Uses a mock `claude` binary -- no real API calls.

**Files:**
- Create: `tests/test_end_to_end.py`

- [ ] **Step 1: Write end-to-end test**

```python
# tests/test_end_to_end.py
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
    assert (workspace / "feedback.json").is_file()

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
```

- [ ] **Step 2: Run all tests**

Run: `cd /Users/mrizzi/git/cloned/skill-litmus && python3 -m pytest tests/ -v --timeout=120`
Expected: all tests pass (11 total across 4 test files)

- [ ] **Step 3: Make all scripts executable**

```bash
chmod +x plugins/skill-litmus/scripts/run-evals.sh
chmod +x plugins/skill-litmus/scripts/post-results.sh
chmod +x plugins/skill-litmus/scripts/aggregate_benchmark.py
chmod +x plugins/skill-litmus/scripts/render_summary.py
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_end_to_end.py
git add plugins/skill-litmus/scripts/run-evals.sh
git add plugins/skill-litmus/scripts/post-results.sh
git add plugins/skill-litmus/scripts/aggregate_benchmark.py
git add plugins/skill-litmus/scripts/render_summary.py
git commit -m "test: add end-to-end integration test and make scripts executable"
```
