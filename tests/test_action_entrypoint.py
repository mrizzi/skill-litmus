"""Tests for action-entrypoint.sh event routing and env var threading."""
import json
import os
import stat
import subprocess

import pytest
import yaml

SCRIPT = "plugins/skill-litmus/scripts/action-entrypoint.sh"


@pytest.fixture
def mock_bin(tmp_path):
    """Create a mock-bin directory with stub CLIs that log invocations."""
    mock_dir = tmp_path / "mock-bin"
    mock_dir.mkdir()
    log_file = tmp_path / "mock.log"

    for name in ("gh", "git", "claude"):
        stub = mock_dir / name
        if name == "gh":
            stub.write_text(f'''#!/usr/bin/env bash
if [[ -z "${{GH_TOKEN:-}}" && -z "${{GITHUB_TOKEN:-}}" ]]; then
    echo "gh: To use GitHub CLI in a GitHub Actions workflow, set the GH_TOKEN environment variable." >&2
    exit 4
fi
echo "{name} $*" >> "{log_file}"
case "$*" in
  *"repo view"*) echo "main" ;;
  *"pr view"*baseRefOid*) echo "abc123" ;;
  *"diff --name-only"*) echo "" ;;
  *) echo "mock-ok" ;;
esac
exit 0
''')
        else:
            stub.write_text(f'''#!/usr/bin/env bash
echo "{name} $*" >> "{log_file}"
case "$*" in
  *"repo view"*) echo "main" ;;
  *"pr view"*baseRefOid*) echo "abc123" ;;
  *"diff --name-only"*) echo "" ;;
  *) echo "mock-ok" ;;
esac
exit 0
''')
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

    return str(mock_dir), str(log_file)


@pytest.fixture
def action_scripts(tmp_path):
    """Create stub downstream scripts that log their invocations."""
    scripts_dir = tmp_path / "action" / "plugins" / "skill-litmus" / "scripts"
    scripts_dir.mkdir(parents=True)
    log_file = tmp_path / "scripts.log"

    for name in ("run-pr-evals.sh", "run-evals.sh", "post-results.sh",
                 "capture-feedback.sh"):
        stub = scripts_dir / name
        stub.write_text(f'''#!/usr/bin/env bash
echo "{name} $*" >> "{log_file}"
exit 0
''')
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

    return str(tmp_path / "action"), str(log_file)


def _base_env(tmp_path, action_path, mock_dir):
    """Build a minimal env dict for running action-entrypoint.sh."""
    env = os.environ.copy()
    env["PATH"] = mock_dir + ":" + env["PATH"]
    env["ACTION_PATH"] = action_path
    env["EVALS_DIR"] = str(tmp_path / "evals") + "/"
    env["RUNNER_TEMP"] = str(tmp_path / "runner-temp")
    env["GH_TOKEN"] = "test-token"
    os.makedirs(env["RUNNER_TEMP"], exist_ok=True)
    env.pop("SKILLS_DIR", None)
    env.pop("BASELINE_BRANCH", None)
    env.pop("PR_URL", None)
    env.pop("COMMENT_ID", None)
    env.pop("AUTHOR_ASSOC", None)
    return env


def _make_eval_suite(evals_dir, skill_name="test-skill"):
    """Create a minimal evals directory with one suite."""
    suite_dir = evals_dir / skill_name
    suite_dir.mkdir(parents=True)
    (suite_dir / "evals.json").write_text(json.dumps({
        "skill_name": skill_name,
        "plugin": "test-plugin",
        "evals": [{"id": 1, "prompt": "x", "expected_output": "y",
                    "assertions": ["z"]}],
    }))


# --- pull_request event ---

def test_pull_request_missing_pr_number(tmp_path, mock_bin, action_scripts):
    mock_dir, _ = mock_bin
    action_path, _ = action_scripts
    env = _base_env(tmp_path, action_path, mock_dir)
    env["GITHUB_EVENT_NAME"] = "pull_request"
    env["PR_BASE_SHA"] = "abc123"
    env.pop("PR_NUMBER", None)

    result = subprocess.run(
        ["bash", SCRIPT], capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0
    assert "PR_NUMBER is required" in result.stderr


def test_pull_request_calls_run_pr_evals(tmp_path, mock_bin, action_scripts):
    mock_dir, _ = mock_bin
    action_path, scripts_log = action_scripts
    env = _base_env(tmp_path, action_path, mock_dir)
    env["GITHUB_EVENT_NAME"] = "pull_request"
    env["PR_BASE_SHA"] = "abc123"
    env["PR_NUMBER"] = "42"

    result = subprocess.run(
        ["bash", SCRIPT], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr

    log = open(scripts_log).read()
    assert "run-pr-evals.sh" in log
    assert "--pr-number 42" in log
    assert "--base-sha abc123" in log


def test_pull_request_threads_pr_number(tmp_path, mock_bin, action_scripts):
    """PR_NUMBER env var reaches run-pr-evals.sh via --pr-number flag."""
    mock_dir, _ = mock_bin
    action_path, scripts_log = action_scripts
    env = _base_env(tmp_path, action_path, mock_dir)
    env["GITHUB_EVENT_NAME"] = "pull_request"
    env["PR_BASE_SHA"] = "abc123"
    env["PR_NUMBER"] = "99"

    result = subprocess.run(
        ["bash", SCRIPT], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr

    log = open(scripts_log).read()
    assert "--pr-number 99" in log


# --- push event ---

def test_push_calls_run_evals_and_baseline(tmp_path, mock_bin, action_scripts):
    mock_dir, _ = mock_bin
    action_path, scripts_log = action_scripts
    evals_dir = tmp_path / "evals"
    _make_eval_suite(evals_dir)

    env = _base_env(tmp_path, action_path, mock_dir)
    env["GITHUB_EVENT_NAME"] = "push"
    env["GITHUB_SHA"] = "deadbeef"

    result = subprocess.run(
        ["bash", SCRIPT], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr

    log = open(scripts_log).read()
    assert "run-evals.sh" in log
    assert "post-results.sh baseline" in log
    assert "--commit-hash deadbeef" in log


def test_push_skips_when_no_evals(tmp_path, mock_bin, action_scripts):
    mock_dir, _ = mock_bin
    action_path, scripts_log = action_scripts
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir()

    env = _base_env(tmp_path, action_path, mock_dir)
    env["GITHUB_EVENT_NAME"] = "push"
    env["GITHUB_SHA"] = "deadbeef"

    result = subprocess.run(
        ["bash", SCRIPT], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0
    assert not os.path.exists(scripts_log)


# --- issue_comment event ---

def test_issue_comment_skips_non_pr(tmp_path, mock_bin, action_scripts):
    mock_dir, _ = mock_bin
    action_path, _ = action_scripts
    env = _base_env(tmp_path, action_path, mock_dir)
    env["GITHUB_EVENT_NAME"] = "issue_comment"
    env["PR_URL"] = ""
    env["COMMENT_ID"] = "111"
    env["AUTHOR_ASSOC"] = "OWNER"

    result = subprocess.run(
        ["bash", SCRIPT], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0
    assert "not on a PR" in result.stdout


def test_issue_comment_skips_non_command(tmp_path, mock_bin, action_scripts):
    mock_dir, _ = mock_bin
    action_path, _ = action_scripts
    env = _base_env(tmp_path, action_path, mock_dir)
    env["GITHUB_EVENT_NAME"] = "issue_comment"
    env["PR_URL"] = "https://api.github.com/repos/o/r/pulls/1"
    env["COMMENT_ID"] = "111"
    env["AUTHOR_ASSOC"] = "OWNER"

    comment_file = tmp_path / "runner-temp" / "comment_body.txt"
    comment_file.write_text("just a regular comment\n")

    result = subprocess.run(
        ["bash", SCRIPT], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0
    assert "does not match" in result.stdout


def test_issue_comment_permission_gate(tmp_path, mock_bin, action_scripts):
    mock_dir, _ = mock_bin
    action_path, scripts_log = action_scripts
    env = _base_env(tmp_path, action_path, mock_dir)
    env["GITHUB_EVENT_NAME"] = "issue_comment"
    env["PR_URL"] = "https://api.github.com/repos/o/r/pulls/1"
    env["COMMENT_ID"] = "111"
    env["AUTHOR_ASSOC"] = "NONE"
    env["PR_NUMBER"] = "1"

    comment_file = tmp_path / "runner-temp" / "comment_body.txt"
    comment_file.write_text("/skill-litmus rerun\n")

    result = subprocess.run(
        ["bash", SCRIPT], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0

    log = open(scripts_log).read()
    assert "post-results.sh comment-reply" in log
    assert "--reaction -1" in log


def test_issue_comment_rerun_uses_pr_number(tmp_path, mock_bin, action_scripts):
    mock_dir, mock_log = mock_bin
    action_path, scripts_log = action_scripts
    env = _base_env(tmp_path, action_path, mock_dir)
    env["GITHUB_EVENT_NAME"] = "issue_comment"
    env["PR_URL"] = "https://api.github.com/repos/o/r/pulls/55"
    env["COMMENT_ID"] = "111"
    env["AUTHOR_ASSOC"] = "OWNER"
    env["PR_NUMBER"] = "55"

    comment_file = tmp_path / "runner-temp" / "comment_body.txt"
    comment_file.write_text("/skill-litmus rerun\n")

    result = subprocess.run(
        ["bash", SCRIPT], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr

    cli_log = open(mock_log).read()
    assert "gh pr checkout 55" in cli_log
    assert "gh pr view 55" in cli_log

    log = open(scripts_log).read()
    assert "run-pr-evals.sh" in log
    assert "--pr-number 55" in log


def test_issue_comment_invalid_comment_id(tmp_path, mock_bin, action_scripts):
    mock_dir, _ = mock_bin
    action_path, _ = action_scripts
    env = _base_env(tmp_path, action_path, mock_dir)
    env["GITHUB_EVENT_NAME"] = "issue_comment"
    env["PR_URL"] = "https://api.github.com/repos/o/r/pulls/1"
    env["COMMENT_ID"] = "not-a-number"
    env["AUTHOR_ASSOC"] = "OWNER"

    comment_file = tmp_path / "runner-temp" / "comment_body.txt"
    comment_file.write_text("/skill-litmus rerun\n")

    result = subprocess.run(
        ["bash", SCRIPT], capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0
    assert "invalid comment ID" in result.stderr


# --- unsupported event ---

def test_unsupported_event_exits_cleanly(tmp_path, mock_bin, action_scripts):
    mock_dir, _ = mock_bin
    action_path, _ = action_scripts
    env = _base_env(tmp_path, action_path, mock_dir)
    env["GITHUB_EVENT_NAME"] = "workflow_dispatch"

    result = subprocess.run(
        ["bash", SCRIPT], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0
    assert "Unsupported event" in result.stdout


# --- action.yml contract tests ---

def test_action_yml_sets_required_env_vars():
    """action.yml must pass all env vars the entrypoint and downstream scripts need."""
    with open("action.yml") as f:
        data = yaml.safe_load(f)
    step = next(s for s in data["runs"]["steps"]
                if s.get("name") == "Run evals")
    env_keys = set(step.get("env", {}).keys())
    required = {"GH_TOKEN", "EVALS_DIR", "ACTION_PATH",
                "PR_NUMBER", "PR_BASE_SHA"}
    missing = required - env_keys
    assert not missing, f"action.yml 'Run evals' step missing env vars: {missing}"


# --- gh authentication tests ---

def test_gh_fails_without_token(tmp_path, mock_bin, action_scripts):
    """Mock gh must reject calls when GH_TOKEN is unset, like real gh in CI."""
    mock_dir, _ = mock_bin
    action_path, scripts_log = action_scripts
    env = _base_env(tmp_path, action_path, mock_dir)
    env["GITHUB_EVENT_NAME"] = "issue_comment"
    env["PR_URL"] = "https://api.github.com/repos/o/r/pulls/1"
    env["COMMENT_ID"] = "111"
    env["AUTHOR_ASSOC"] = "OWNER"
    env["PR_NUMBER"] = "1"
    env.pop("GH_TOKEN", None)
    env.pop("GITHUB_TOKEN", None)

    comment_file = tmp_path / "runner-temp" / "comment_body.txt"
    comment_file.write_text("/skill-litmus rerun\n")

    result = subprocess.run(
        ["bash", SCRIPT], capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0
    assert "GH_TOKEN" in result.stderr
