# Release Reliability: Action Integration Testing

## Problem

skill-litmus v0.1.2 shipped a heredoc syntax error (#9) that broke the
entire action, and v0.1.3 shipped a PR number detection failure (#11)
that broke PR review posting. Both bugs are in the `action.yml`
composite action's embedded bash script, which is validated syntactically
(`bash -n`, actionlint, shellcheck) but never actually executed in CI.

The existing test suite (33 pytest tests) covers individual scripts
thoroughly but cannot catch bugs in the action's event routing, env var
threading, or YAML-embedded script expansion.

## Solution

Extract the embedded script from `action.yml` into a standalone
`action-entrypoint.sh`, then test it with pytest using the same
mock-subprocess patterns already established in the test suite. Add a
separate optional CI job for real-API integration tests.

## Design

### 1. Extract `action-entrypoint.sh`

**File:** `plugins/skill-litmus/scripts/action-entrypoint.sh`

The "Run evals" step in `action.yml` (lines 55-307) contains ~250 lines
of bash handling event routing, command parsing, and script
orchestration. Extract this verbatim into a standalone script.

The `action.yml` step becomes:

```yaml
- name: Run evals
  shell: bash
  env:
    EVALS_DIR: ${{ inputs.evals-dir }}
    SKILLS_DIR: ${{ inputs.skills-dir }}
    BASELINE_BRANCH: ${{ inputs.baseline-branch }}
    COMMENT_ID: ${{ github.event.comment.id }}
    AUTHOR_ASSOC: ${{ github.event.comment.author_association }}
    PR_URL: ${{ github.event.issue.pull_request.url }}
    PR_NUMBER: ${{ github.event.pull_request.number || github.event.issue.number }}
    PR_BASE_SHA: ${{ github.event.pull_request.base.sha }}
    ACTION_PATH: ${{ github.action_path }}
  run: bash "${ACTION_PATH}/plugins/skill-litmus/scripts/action-entrypoint.sh"
```

The extracted script expects the same env vars and calls the same
downstream scripts. No logic changes.

`SCRIPT_DIR` in the extracted script must be derived from `ACTION_PATH`
(not `BASH_SOURCE`) since `action.yml` sets `ACTION_PATH` to the action
root:

```bash
SCRIPT_DIR="${ACTION_PATH}/plugins/skill-litmus/scripts"
```

### 2. pytest tests for `action-entrypoint.sh`

**File:** `tests/test_action_entrypoint.py`

Uses the same subprocess + mock CLI pattern as existing tests. Mock
stubs for `claude`, `gh`, `git`, and `jq` record invocation arguments
to a log file for assertion.

**Test cases:**

| Test | Event | Validates |
|------|-------|-----------|
| `test_pull_request_routes_to_run_pr_evals` | `pull_request` | Calls `run-pr-evals.sh` with `--pr-number` |
| `test_pull_request_threads_pr_number` | `pull_request` | `PR_NUMBER` reaches `post-results.sh` via `run-pr-evals.sh` |
| `test_push_routes_to_run_evals_and_baseline` | `push` | Calls `run-evals.sh` + `post-results.sh baseline` per suite |
| `test_issue_comment_skips_non_pr` | `issue_comment` | Exits 0 when `PR_URL` is empty |
| `test_issue_comment_skips_non_command` | `issue_comment` | Exits 0 when comment doesn't match `/skill-litmus` |
| `test_issue_comment_permission_gate` | `issue_comment` | Rejects non-collaborators |
| `test_issue_comment_rerun` | `issue_comment` | `rerun` command calls `gh pr checkout "$PR_NUMBER"` |
| `test_issue_comment_feedback` | `issue_comment` | `feedback` command calls `capture-feedback.sh` |
| `test_unsupported_event_exits_cleanly` | `workflow_dispatch` | Exits 0 with message |

**Mock approach:**

Each mock CLI is a bash stub that appends its arguments to a shared log
file (`$MOCK_LOG`). Tests read this log to assert on exact invocations:

```bash
#!/usr/bin/env bash
echo "gh $*" >> "$MOCK_LOG"
# Return canned responses based on arguments
case "$*" in
  *"pr checkout"*) exit 0 ;;
  *"pr view"*baseRefOid*) echo "abc123" ;;
  *"repo view"*) echo "main" ;;
  *) exit 0 ;;
esac
```

**Fixture setup:**

Tests create a minimal eval suite directory with `evals.json` and a
mock `.claude-plugin/plugin.json` in `tmp_path`, then set env vars to
point at it.

### 3. Real API integration test

**New CI job** in `.github/workflows/test-action.yml`, runs after
`unit-tests`.

**Test fixture:** `.github/test-fixtures/ci-eval/evals.json`

```json
{
  "skill_name": "ci-eval",
  "plugin": "skill-litmus",
  "evals": [
    {
      "id": 1,
      "prompt": "Echo the text 'hello world' to stdout",
      "expected_output": "The text hello world printed to stdout",
      "files": [],
      "assertions": ["The output contains the text hello world"]
    }
  ]
}
```

**Behavior:**
- Gated on `ANTHROPIC_API_KEY` secret — posts `::notice` and skips when
  unavailable (fork PRs, unconfigured repos)
- Installs Claude CLI
- Runs `run-evals.sh` with the test fixture
- Verifies output structure: `benchmark.json`, `summary.md`,
  `eval-1/grading.json`, `eval-1/timing.json`
- Asserts `total_evals == 1` in `benchmark.json`
- Cost: ~$0.05 per run

### 4. Workflow updates

**File:** `.github/workflows/test-action.yml`

Changes:
- Add `.github/test-fixtures/**` to path filters (both `pull_request`
  and `push`)
- Add `integration` job (Section 3) after `unit-tests`
- No changes to `lint` or `unit-tests` jobs (shellcheck already scans
  all `.sh` files in `plugins/skill-litmus/scripts/`, and pytest already
  runs all `tests/test_*.py`)

Pipeline: `lint` -> `unit-tests` (mock-based, includes
action-entrypoint tests) -> `integration` (real API, optional)

### 5. Cleanup

- Delete `docs/future/integration-test-job.md` (superseded by this
  design)

## Files to Create

| File | Purpose |
|------|---------|
| `plugins/skill-litmus/scripts/action-entrypoint.sh` | Extracted action logic |
| `tests/test_action_entrypoint.py` | pytest tests for action routing |
| `.github/test-fixtures/ci-eval/evals.json` | Minimal eval fixture |

## Files to Modify

| File | Change |
|------|--------|
| `action.yml` | Replace embedded script with one-liner calling `action-entrypoint.sh` |
| `.github/workflows/test-action.yml` | Add path filter + integration job |

## Files to Delete

| File | Reason |
|------|--------|
| `docs/future/integration-test-job.md` | Superseded |

## Verification

1. Run `pytest tests/ -v` locally — all existing + new tests pass
2. Run `bash -n plugins/skill-litmus/scripts/action-entrypoint.sh` —
   syntax valid
3. Verify `action.yml` is syntactically valid (actionlint if available)
4. Push to a PR branch and confirm CI pipeline runs all three jobs
5. Verify the integration job skips gracefully without `ANTHROPIC_API_KEY`
