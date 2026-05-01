# Human Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add human-in-the-loop review to the skill-litmus pipeline via PR slash commands (`/skill-litmus feedback`, `rerun`, `iterate`).

**Architecture:** Three slash commands processed by the GitHub Action's `issue_comment` event path. PR logic extracted into a shared script (`run-pr-evals.sh`). Feedback parsed deterministically by `capture-feedback.sh` and stored as `feedback.json`. `render_summary.py` appends a discoverable feedback template. The iterate command invokes `claude -p` with develop-eval iteration logic, gated to maintainers only.

**Tech Stack:** Bash scripts, Python 3 (stdlib only), GitHub Actions composite action, `gh` CLI, `jq`.

---

### Task 1: capture-feedback.sh — Tests

**Files:**
- Create: `tests/test_capture_feedback.py`

This script has two input modes: `--comment` (parses a PR comment body) and `--eval` flags (CLI). Both write the same `feedback.json` format to `--output`.

- [ ] **Step 1: Write test for CLI flag mode**

```python
# tests/test_capture_feedback.py
import json
import subprocess

SCRIPT = "plugins/skill-litmus/scripts/capture-feedback.sh"


def test_cli_flag_mode(tmp_path):
    output = tmp_path / "feedback.json"
    result = subprocess.run(
        [
            "bash", SCRIPT,
            "--output", str(output),
            "--eval", "1", "The axis labels are unreadable",
            "--eval", "2", "",
            "--eval", "3", "Wrong date format",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    feedback = json.loads(output.read_text())
    assert feedback == {
        "eval-1": "The axis labels are unreadable",
        "eval-2": "",
        "eval-3": "Wrong date format",
    }
```

- [ ] **Step 2: Write test for comment body mode**

```python
def test_comment_body_mode(tmp_path):
    output = tmp_path / "feedback.json"
    comment = """/skill-litmus feedback
eval-1: The axis labels are unreadable
eval-2:
eval-3: Months are in alphabetical order"""
    result = subprocess.run(
        [
            "bash", SCRIPT,
            "--output", str(output),
            "--comment", comment,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    feedback = json.loads(output.read_text())
    assert feedback == {
        "eval-1": "The axis labels are unreadable",
        "eval-2": "",
        "eval-3": "Months are in alphabetical order",
    }
```

- [ ] **Step 3: Write test for merge with existing feedback**

```python
def test_merge_existing_feedback(tmp_path):
    output = tmp_path / "feedback.json"
    output.write_text(json.dumps({
        "eval-1": "old feedback",
        "eval-2": "keep this",
    }))
    result = subprocess.run(
        [
            "bash", SCRIPT,
            "--output", str(output),
            "--eval", "1", "new feedback",
            "--eval", "3", "brand new",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    feedback = json.loads(output.read_text())
    assert feedback == {
        "eval-1": "new feedback",
        "eval-2": "keep this",
        "eval-3": "brand new",
    }
```

- [ ] **Step 4: Write test for missing output path error**

```python
def test_missing_output_arg():
    result = subprocess.run(
        ["bash", SCRIPT, "--eval", "1", "text"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "output" in result.stderr.lower()
```

- [ ] **Step 5: Write test for no feedback entries error**

```python
def test_no_feedback_entries(tmp_path):
    output = tmp_path / "feedback.json"
    result = subprocess.run(
        ["bash", SCRIPT, "--output", str(output)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "no feedback" in result.stderr.lower()
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_capture_feedback.py -v`
Expected: All 5 tests FAIL (script doesn't exist yet).

- [ ] **Step 7: Commit**

```bash
git add tests/test_capture_feedback.py
git commit -m "test: add tests for capture-feedback.sh"
```

---

### Task 2: capture-feedback.sh — Implementation

**Files:**
- Create: `plugins/skill-litmus/scripts/capture-feedback.sh`

- [ ] **Step 1: Write capture-feedback.sh**

```bash
#!/usr/bin/env bash
# Parse per-eval feedback and write feedback.json.
# See docs/specs/2026-04-30-human-review-design.md Section 3.2.
#
# Usage:
#   capture-feedback.sh --output <path> --eval <id> "<text>" [--eval <id> "<text>" ...]
#   capture-feedback.sh --output <path> --comment "<body>"

set -euo pipefail

OUTPUT=""
COMMENT=""
declare -a EVAL_IDS=()
declare -a EVAL_TEXTS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)  OUTPUT="$2";  shift 2 ;;
        --comment) COMMENT="$2"; shift 2 ;;
        --eval)
            EVAL_IDS+=("$2")
            EVAL_TEXTS+=("$3")
            shift 3
            ;;
        *) echo "Error: unknown argument: $1" >&2; exit 1 ;;
    esac
done

[[ -z "$OUTPUT" ]] && echo "Error: --output required" >&2 && exit 1

if [[ -n "$COMMENT" ]]; then
    while IFS= read -r line; do
        if [[ "$line" =~ ^eval-([0-9]+):[[:space:]]*(.*) ]]; then
            EVAL_IDS+=("${BASH_REMATCH[1]}")
            EVAL_TEXTS+=("${BASH_REMATCH[2]}")
        fi
    done <<< "$COMMENT"
fi

if [[ ${#EVAL_IDS[@]} -eq 0 ]]; then
    echo "Error: no feedback entries provided" >&2
    exit 1
fi

python3 - "$OUTPUT" "${EVAL_IDS[@]}" -- "${EVAL_TEXTS[@]}" <<'PYEOF'
import json
import os
import sys

args = sys.argv[1:]
output_path = args[0]
rest = args[1:]
sep = rest.index("--")
ids = rest[:sep]
texts = rest[sep + 1:]

new_feedback = {f"eval-{i}": t for i, t in zip(ids, texts)}

if os.path.exists(output_path):
    with open(output_path) as f:
        existing = json.load(f)
    existing.update(new_feedback)
    merged = existing
else:
    merged = new_feedback

with open(output_path, "w") as f:
    json.dump(merged, f, indent=2)
    f.write("\n")
PYEOF

echo "Feedback written to $OUTPUT"
```

- [ ] **Step 2: Make the script executable**

Run: `chmod +x plugins/skill-litmus/scripts/capture-feedback.sh`

- [ ] **Step 3: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_capture_feedback.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add plugins/skill-litmus/scripts/capture-feedback.sh
git commit -m "feat: add capture-feedback.sh for per-eval feedback"
```

---

### Task 3: render_summary.py — Feedback Template

**Files:**
- Modify: `plugins/skill-litmus/scripts/render_summary.py:78-119`
- Modify: `tests/test_render_summary.py`

- [ ] **Step 1: Write test for feedback template in summary**

Add to the end of `tests/test_render_summary.py`:

```python
def test_feedback_template_included(workspace):
    setup_workspace_with_benchmark(workspace)

    result = run_render(workspace.root)
    assert result.returncode == 0

    summary = (workspace.root / "summary.md").read_text()
    assert "### Provide feedback" in summary
    assert "/skill-litmus feedback" in summary
    assert "eval-1:" in summary
    assert "eval-2:" in summary


def test_feedback_template_lists_all_eval_ids(workspace):
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
    workspace.add_eval(
        5,
        grading={
            "eval_id": 5,
            "assertions": [
                {"assertion": "B", "passed": True, "reasoning": "ok"},
            ],
        },
        timing={"eval_id": 5, "duration_seconds": 10.0},
    )
    subprocess.run(
        [sys.executable, AGGREGATE_SCRIPT, "--results", str(workspace.root)],
        check=True,
    )

    result = run_render(workspace.root)
    assert result.returncode == 0

    summary = (workspace.root / "summary.md").read_text()
    assert "eval-1:" in summary
    assert "eval-5:" in summary
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_render_summary.py::test_feedback_template_included tests/test_render_summary.py::test_feedback_template_lists_all_eval_ids -v`
Expected: FAIL (template not generated yet).

- [ ] **Step 3: Add feedback template to render_summary.py**

In `plugins/skill-litmus/scripts/render_summary.py`, add the feedback template section after the failed assertions block. Insert after the `if failed_results:` block (after line 110), before `output = "\n".join(lines)`:

```python
    eval_ids = [r["eval_id"] for r in s["results"]]
    lines.append("")
    lines.append("### Provide feedback")
    lines.append("")
    lines.append(
        "Copy the block below, fill in your notes, and post as a PR comment:"
    )
    lines.append("")
    lines.append("```")
    lines.append("/skill-litmus feedback")
    for eid in eval_ids:
        lines.append(f"eval-{eid}:")
    lines.append("```")
    lines.append("")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_render_summary.py -v`
Expected: All 6 tests PASS (4 existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add plugins/skill-litmus/scripts/render_summary.py tests/test_render_summary.py
git commit -m "feat: add feedback template to summary output"
```

---

### Task 4: run-evals.sh — Remove Auto-Generated feedback.json

**Files:**
- Modify: `plugins/skill-litmus/scripts/run-evals.sh:256-257`
- Modify: `tests/test_run_evals.py:100`
- Modify: `tests/test_end_to_end.py:131`

- [ ] **Step 1: Update test_run_evals.py — remove feedback.json assertion**

In `tests/test_run_evals.py`, delete line 100:

```python
    assert (workspace / "feedback.json").is_file()
```

- [ ] **Step 2: Update test_end_to_end.py — remove feedback.json assertion**

In `tests/test_end_to_end.py`, delete line 131:

```python
    assert (workspace / "feedback.json").is_file()
```

- [ ] **Step 3: Remove feedback.json creation from run-evals.sh**

In `plugins/skill-litmus/scripts/run-evals.sh`, delete lines 256-257:

```bash
# --- Create empty feedback.json ---
echo '{}' > "$WORKSPACE/feedback.json"
```

- [ ] **Step 4: Run all tests to verify nothing breaks**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add plugins/skill-litmus/scripts/run-evals.sh tests/test_run_evals.py tests/test_end_to_end.py
git commit -m "refactor: remove auto-generated feedback.json from run-evals.sh

feedback.json is now human-authored only, per agentskills.io model."
```

---

### Task 5: run-pr-evals.sh — Extract Shared PR Logic

**Files:**
- Create: `plugins/skill-litmus/scripts/run-pr-evals.sh`
- Create: `tests/test_run_pr_evals.py`

This script extracts the PR logic from `action.yml` lines 47-91 into a reusable script. Both the `pull_request` event path and the `rerun` command call it.

- [ ] **Step 1: Write test for run-pr-evals.sh**

```python
# tests/test_run_pr_evals.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_run_pr_evals.py -v`
Expected: FAIL (script doesn't exist yet).

- [ ] **Step 3: Write run-pr-evals.sh**

```bash
#!/usr/bin/env bash
# Shared PR logic — runs changed skills and posts results.
# See docs/specs/2026-04-30-human-review-design.md Section 3.6.
#
# Usage:
#   run-pr-evals.sh --base-sha <sha> --evals-dir <path> \
#                    --workspace-root <dir> --changed-files <text> \
#                    [--skills-dir <path>] [--baseline-branch <branch>]

set -euo pipefail

BASE_SHA=""
EVALS_DIR=""
WORKSPACE_ROOT=""
CHANGED_FILES=""
SKILLS_DIR=""
BASELINE_BRANCH=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --base-sha)        BASE_SHA="$2";        shift 2 ;;
        --evals-dir)       EVALS_DIR="$2";       shift 2 ;;
        --workspace-root)  WORKSPACE_ROOT="$2";  shift 2 ;;
        --changed-files)   CHANGED_FILES="$2";   shift 2 ;;
        --skills-dir)      SKILLS_DIR="$2";      shift 2 ;;
        --baseline-branch) BASELINE_BRANCH="$2"; shift 2 ;;
        *) echo "Error: unknown argument: $1" >&2; exit 1 ;;
    esac
done

[[ -z "$BASE_SHA" ]]       && echo "Error: --base-sha required" >&2 && exit 1
[[ -z "$EVALS_DIR" ]]      && echo "Error: --evals-dir required" >&2 && exit 1
[[ -z "$WORKSPACE_ROOT" ]] && echo "Error: --workspace-root required" >&2 && exit 1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -z "$BASELINE_BRANCH" ]]; then
    BASELINE_BRANCH=$(gh repo view --json defaultBranchRef -q '.defaultBranchRef.name' 2>/dev/null || echo "main")
fi

if [[ -z "$CHANGED_FILES" ]]; then
    CHANGED_FILES=$(git diff --name-only "$BASE_SHA"...HEAD 2>/dev/null || true)
fi

EVALS_TO_RUN=()
for evals_json in ${EVALS_DIR}*/evals.json; do
    [[ ! -f "$evals_json" ]] && continue
    skill_dir="$(dirname "$evals_json")"
    skill_name="$(basename "$skill_dir")"

    if echo "$CHANGED_FILES" | grep -qE "(${skill_dir}/|${SKILLS_DIR:-skills/}.*${skill_name})"; then
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

    baseline_args=()
    baseline_file="$skill_dir/baselines/latest/benchmark.json"
    baseline_tmp="$WORKSPACE_ROOT/baseline-${skill_name}.json"
    if git show "$BASELINE_BRANCH:$baseline_file" > "$baseline_tmp" 2>/dev/null; then
        baseline_args=(--baseline "$baseline_tmp")
    fi

    bash "$SCRIPT_DIR/run-evals.sh" \
        --evals "$evals_json" \
        --skill "$skill_name" \
        --workspace "$ws" \
        ${baseline_args[@]+"${baseline_args[@]}"}

    WORKSPACE_ARGS+=("--workspace" "$ws")
done

if [[ ${#WORKSPACE_ARGS[@]} -gt 0 ]]; then
    bash "$SCRIPT_DIR/post-results.sh" pr "${WORKSPACE_ARGS[@]}"
fi

echo "PR evals complete."
```

- [ ] **Step 4: Make the script executable**

Run: `chmod +x plugins/skill-litmus/scripts/run-pr-evals.sh`

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_run_pr_evals.py -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add plugins/skill-litmus/scripts/run-pr-evals.sh tests/test_run_pr_evals.py
git commit -m "feat: add run-pr-evals.sh shared PR logic"
```

---

### Task 6: post-results.sh — Add comment-reply Subcommand

**Files:**
- Modify: `plugins/skill-litmus/scripts/post-results.sh:99-105`

- [ ] **Step 1: Add comment-reply mode to post-results.sh**

Add a new case before the `*)` fallback in `post-results.sh`, after the `baseline)` block ends at line 99:

```bash
    comment-reply)
        COMMENT_ID=""
        BODY=""
        REACTION=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                --comment-id) COMMENT_ID="$2"; shift 2 ;;
                --body)       BODY="$2";       shift 2 ;;
                --reaction)   REACTION="$2";   shift 2 ;;
                *) echo "Error: unknown argument: $1" >&2; exit 1 ;;
            esac
        done

        if [[ -n "$REACTION" && -n "$COMMENT_ID" ]]; then
            gh api "repos/{owner}/{repo}/issues/comments/$COMMENT_ID/reactions" \
                -X POST -f content="$REACTION" > /dev/null 2>&1 || true
        fi

        if [[ -n "$BODY" ]]; then
            PR_NUMBER=$(gh pr view --json number -q '.number' 2>/dev/null || true)
            if [[ -z "$PR_NUMBER" ]]; then
                echo "Error: could not detect PR number" >&2
                exit 1
            fi
            gh api "repos/{owner}/{repo}/issues/$PR_NUMBER/comments" \
                -X POST -f body="$BODY" > /dev/null
            echo "Posted reply to PR #$PR_NUMBER"
        fi
        ;;
```

- [ ] **Step 2: Update usage strings**

In line 14, change:

```bash
[[ -z "$MODE" ]] && echo "Usage: post-results.sh {pr|baseline} [options]" >&2 && exit 1
```

to:

```bash
[[ -z "$MODE" ]] && echo "Usage: post-results.sh {pr|baseline|comment-reply} [options]" >&2 && exit 1
```

And in the final `*)` fallback at the end of the file:

```bash
        echo "Usage: post-results.sh {pr|baseline|comment-reply} [options]" >&2
```

- [ ] **Step 3: Run existing tests to verify nothing breaks**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add plugins/skill-litmus/scripts/post-results.sh
git commit -m "feat: add comment-reply subcommand to post-results.sh"
```

---

### Task 7: action.yml — Add issue_comment Routing

**Files:**
- Modify: `action.yml`

This is the integration task. The `pull_request` path is refactored to call `run-pr-evals.sh`, and the new `issue_comment` path handles all three slash commands.

- [ ] **Step 1: Rewrite action.yml**

Replace the entire content of `action.yml` with:

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

        if [[ "$EVENT" == "pull_request" ]]; then
          # --- PR mode: run changed skills via shared script ---
          BASE_SHA="${{ github.event.pull_request.base.sha }}"
          CHANGED=$(git diff --name-only "$BASE_SHA"...HEAD)

          bash "$SCRIPT_DIR/run-pr-evals.sh" \
            --base-sha "$BASE_SHA" \
            --evals-dir "${EVALS_DIR}" \
            --workspace-root "$WORKSPACE_ROOT" \
            --changed-files "$CHANGED" \
            ${SKILLS_DIR:+--skills-dir "$SKILLS_DIR"} \
            ${BASELINE_BRANCH:+--baseline-branch "$BASELINE_BRANCH"}

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

        elif [[ "$EVENT" == "issue_comment" ]]; then
          # --- Comment mode: parse /skill-litmus commands ---
          COMMENT_BODY=$(cat <<'COMMENT_EOF'
        ${{ github.event.comment.body }}
        COMMENT_EOF
          )
          COMMENT_ID='${{ github.event.comment.id }}'
          AUTHOR_ASSOC='${{ github.event.comment.author_association }}'

          # Guard: only process on PRs
          PR_URL='${{ github.event.issue.pull_request.url }}'
          if [[ -z "$PR_URL" ]]; then
            echo "Comment is not on a PR — skipping."
            exit 0
          fi

          # Match /skill-litmus command
          if ! echo "$COMMENT_BODY" | head -1 | grep -qE '^/skill-litmus[[:space:]]+(feedback|rerun|iterate)'; then
            echo "Comment does not match /skill-litmus command — skipping."
            exit 0
          fi

          COMMAND=$(echo "$COMMENT_BODY" | head -1 | grep -oE '(feedback|rerun|iterate)')

          # React with eyes to acknowledge
          bash "$SCRIPT_DIR/post-results.sh" comment-reply \
            --comment-id "$COMMENT_ID" --reaction "eyes"

          case "$COMMAND" in
            feedback)
              SKILL_NAME=""
              for evals_json in ${EVALS_DIR}*/evals.json; do
                [[ ! -f "$evals_json" ]] && continue
                SKILL_NAME=$(jq -r '.skill_name' "$evals_json")
                break
              done

              if [[ -z "$SKILL_NAME" ]]; then
                bash "$SCRIPT_DIR/post-results.sh" comment-reply \
                  --comment-id "$COMMENT_ID" --reaction "-1" \
                  --body "Error: could not detect skill. No evals.json found in ${EVALS_DIR}."
                exit 1
              fi

              FEEDBACK_PATH="${EVALS_DIR}${SKILL_NAME}/feedback.json"
              bash "$SCRIPT_DIR/capture-feedback.sh" \
                --output "$FEEDBACK_PATH" \
                --comment "$COMMENT_BODY"

              git add "$FEEDBACK_PATH"
              git commit -m "chore: capture human review feedback" || true
              git push || echo "Warning: git push failed" >&2

              EVAL_LIST=$(python3 -c "
          import json, sys
          fb = json.load(open(sys.argv[1]))
          print(', '.join(sorted(fb.keys())))
          " "$FEEDBACK_PATH")

              bash "$SCRIPT_DIR/post-results.sh" comment-reply \
                --comment-id "$COMMENT_ID" --reaction "+1" \
                --body "Feedback captured for ${EVAL_LIST}. Run \`/skill-litmus iterate\` to generate improvement suggestions."
              ;;

            rerun)
              gh pr checkout "$(gh pr view --json number -q '.number')" --force

              BASE_SHA=$(gh pr view --json baseRefOid -q '.baseRefOid')
              CHANGED=$(git diff --name-only "$BASE_SHA"...HEAD)

              bash "$SCRIPT_DIR/run-pr-evals.sh" \
                --base-sha "$BASE_SHA" \
                --evals-dir "${EVALS_DIR}" \
                --workspace-root "$WORKSPACE_ROOT" \
                --changed-files "$CHANGED" \
                ${SKILLS_DIR:+--skills-dir "$SKILLS_DIR"} \
                ${BASELINE_BRANCH:+--baseline-branch "$BASELINE_BRANCH"}

              bash "$SCRIPT_DIR/post-results.sh" comment-reply \
                --comment-id "$COMMENT_ID" --reaction "+1"
              ;;

            iterate)
              # Permission gate: maintainers only
              if [[ "$AUTHOR_ASSOC" != "OWNER" && "$AUTHOR_ASSOC" != "MEMBER" && "$AUTHOR_ASSOC" != "COLLABORATOR" ]]; then
                bash "$SCRIPT_DIR/post-results.sh" comment-reply \
                  --comment-id "$COMMENT_ID" --reaction "-1" \
                  --body "Only repository maintainers can trigger iteration."
                exit 0
              fi

              SKILL_NAME=""
              FEEDBACK_PATH=""
              for evals_json in ${EVALS_DIR}*/evals.json; do
                [[ ! -f "$evals_json" ]] && continue
                SKILL_NAME=$(jq -r '.skill_name' "$evals_json")
                skill_dir="$(dirname "$evals_json")"
                FEEDBACK_PATH="$skill_dir/feedback.json"
                break
              done

              if [[ ! -f "$FEEDBACK_PATH" ]]; then
                bash "$SCRIPT_DIR/post-results.sh" comment-reply \
                  --comment-id "$COMMENT_ID" --reaction "-1" \
                  --body "No feedback found. Post \`/skill-litmus feedback\` first."
                exit 0
              fi

              # Find SKILL.md
              SKILL_MD=""
              if [[ -n "${SKILLS_DIR:-}" ]]; then
                SKILL_MD=$(find "$SKILLS_DIR" -path "*/$SKILL_NAME/SKILL.md" -print -quit 2>/dev/null || true)
              fi
              if [[ -z "$SKILL_MD" ]]; then
                SKILL_MD=$(find . -path "*/$SKILL_NAME/SKILL.md" -not -path "*/node_modules/*" -print -quit 2>/dev/null || true)
              fi

              # Collect grading data from workspace
              GRADING_CONTEXT=""
              for grading in $(find "$WORKSPACE_ROOT" -name "grading.json" 2>/dev/null); do
                GRADING_CONTEXT="$GRADING_CONTEXT
          --- $(basename "$(dirname "$grading")") ---
          $(cat "$grading")"
              done

              FEEDBACK_CONTENT=$(cat "$FEEDBACK_PATH")
              SKILL_CONTENT=""
              [[ -n "$SKILL_MD" && -f "$SKILL_MD" ]] && SKILL_CONTENT=$(cat "$SKILL_MD")

              ITERATE_PROMPT="You are iterating on a skill based on results and human feedback.

          Current SKILL.md:
          $SKILL_CONTENT

          Human feedback (per-eval):
          $FEEDBACK_CONTENT

          Grading results:
          $GRADING_CONTEXT

          Propose specific improvements to SKILL.md following these principles:
          - Generalize from feedback — fixes should address underlying issues broadly
          - Keep instructions lean — fewer, better instructions outperform exhaustive rules
          - Explain the why — reasoning-based instructions work better than rigid directives

          Respond with ONLY the proposed changes as a unified diff block."

              ITERATE_RESULT=$(claude -p "$ITERATE_PROMPT" \
                --permission-mode dontAsk \
                --allowedTools "Read,Bash,Glob" 2>&1 || true)

              REPLY_BODY="## Proposed SKILL.md Improvements

          Based on feedback for ${SKILL_NAME}:

          $ITERATE_RESULT

          > Apply these changes manually if they look good. Then run \`/skill-litmus rerun\` to verify."

              bash "$SCRIPT_DIR/post-results.sh" comment-reply \
                --comment-id "$COMMENT_ID" --reaction "+1" \
                --body "$REPLY_BODY"
              ;;
          esac

        else
          echo "Unsupported event: $EVENT -- skipping."
          exit 0
        fi
```

- [ ] **Step 2: Run existing tests to verify nothing breaks**

Run: `python3 -m pytest tests/ -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add action.yml
git commit -m "feat: add issue_comment routing and refactor PR path to use run-pr-evals.sh"
```

---

### Task 8: eval-workflow.yml — Add issue_comment Trigger and Artifact Upload

**Note on artifact persistence (spec Section 3.5):** The spec calls for uploading eval workspaces as GitHub Actions artifacts so that `iterate` can access grading data from a previous run. Composite actions cannot call other actions (like `actions/upload-artifact`), so artifact upload/download must be handled in the **workflow template**, not in `action.yml`. This task adds the artifact steps to the template.

**Files:**
- Modify: `plugins/skill-litmus/templates/eval-workflow.yml`

- [ ] **Step 1: Update the workflow template**

Replace the content of `plugins/skill-litmus/templates/eval-workflow.yml` with:

```yaml
# Skill eval workflow — runs evals on PRs and commits baselines on push.
# Copy this file to .github/workflows/eval.yml in your repo.
# Required secret: ANTHROPIC_API_KEY
#
# The action detects the event type and branches behavior:
#   pull_request → runs evals for changed skills, posts PR review
#   push to main → runs all evals, commits baselines
#   issue_comment → handles /skill-litmus commands (feedback, rerun, iterate)

name: Skill Evals

on:
  pull_request:
    paths:
      - 'skills/**/*.md'
      - 'evals/**/evals.json'
  push:
    branches: [main]
    paths:
      - 'skills/**/*.md'
      - 'evals/**/evals.json'
  issue_comment:
    types: [created]

jobs:
  eval:
    runs-on: ubuntu-latest
    # Only run for PR events, push events, or /skill-litmus comments on PRs
    if: >-
      github.event_name == 'pull_request' ||
      github.event_name == 'push' ||
      (github.event_name == 'issue_comment' &&
       github.event.issue.pull_request &&
       startsWith(github.event.comment.body, '/skill-litmus'))
    permissions:
      contents: write
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      # Download previous workspace artifact for iterate command
      - name: Download eval workspace
        if: >-
          github.event_name == 'issue_comment' &&
          contains(github.event.comment.body, '/skill-litmus iterate')
        uses: actions/download-artifact@v4
        with:
          name: skill-litmus-workspace
          path: /tmp/skill-litmus-workspace
        continue-on-error: true

      - uses: mrizzi/skill-litmus@v1
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      # Upload workspace artifact after eval runs (for iterate to use later)
      - name: Upload eval workspace
        if: >-
          github.event_name == 'pull_request' ||
          (github.event_name == 'issue_comment' &&
           contains(github.event.comment.body, '/skill-litmus rerun'))
        uses: actions/upload-artifact@v4
        with:
          name: skill-litmus-workspace
          path: /tmp/skill-litmus-workspace
          retention-days: 90
          if-no-files-found: ignore
```

- [ ] **Step 2: Commit**

```bash
git add plugins/skill-litmus/templates/eval-workflow.yml
git commit -m "feat: add issue_comment trigger to eval workflow template"
```

---

### Task 9: develop-eval SKILL.md — Graceful Missing feedback.json

**Files:**
- Modify: `plugins/skill-litmus/skills/develop-eval/SKILL.md:63-69`

- [ ] **Step 1: Update iteration mode section**

In `plugins/skill-litmus/skills/develop-eval/SKILL.md`, replace lines 63-69:

```markdown
### Iteration mode

When the user provides a workspace with existing results:

1. Read `eval-*/grading.json` files — identify failed assertions.
2. Read `feedback.json` — pick up human review notes.
3. Read the skill's SKILL.md — understand current instructions.
```

with:

```markdown
### Iteration mode

When the user provides a workspace with existing results:

1. Read `eval-*/grading.json` files — identify failed assertions.
2. Read `feedback.json` if it exists — pick up human review notes.
   If `feedback.json` is missing, iterate on failed assertions and
   execution transcripts alone. Do not treat missing feedback as an
   error — it means no human review has occurred yet.
3. Read the skill's SKILL.md — understand current instructions.
```

- [ ] **Step 2: Commit**

```bash
git add plugins/skill-litmus/skills/develop-eval/SKILL.md
git commit -m "fix: handle missing feedback.json gracefully in develop-eval"
```
