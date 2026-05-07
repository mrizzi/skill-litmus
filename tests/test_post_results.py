"""Tests for post-results.sh subcommands."""
import os
import stat
import subprocess

import pytest

SCRIPT = "plugins/skill-litmus/scripts/post-results.sh"


@pytest.fixture
def mock_gh(tmp_path):
    """Mock gh that logs invocations and requires GH_TOKEN."""
    mock_dir = tmp_path / "mock-bin"
    mock_dir.mkdir()
    log_file = tmp_path / "gh.log"
    mock_script = mock_dir / "gh"
    mock_script.write_text(f'''#!/usr/bin/env bash
if [[ -z "${{GH_TOKEN:-}}" && -z "${{GITHUB_TOKEN:-}}" ]]; then
    echo "gh: To use GitHub CLI in a GitHub Actions workflow, set the GH_TOKEN environment variable." >&2
    exit 4
fi
echo "gh $*" >> "{log_file}"
case "$*" in
  *"pulls/"*"/reviews"*"-X POST"*) echo '{{"id": 999}}' ;;
  *"pulls/"*"/reviews"*"-X PUT"*) echo '{{"id": 888}}' ;;
  *"pulls/"*"/reviews"*"--jq"*) ;; # empty output = no existing review
  *) echo "mock-gh-ok" ;;
esac
exit 0
''')
    mock_script.chmod(mock_script.stat().st_mode | stat.S_IEXEC)
    return str(mock_dir), str(log_file)


@pytest.fixture
def mock_gh_with_existing_review(tmp_path):
    """Mock gh that returns an existing review for update tests."""
    mock_dir = tmp_path / "mock-bin-review"
    mock_dir.mkdir()
    log_file = tmp_path / "gh-review.log"
    mock_script = mock_dir / "gh"
    mock_script.write_text(f'''#!/usr/bin/env bash
if [[ -z "${{GH_TOKEN:-}}" && -z "${{GITHUB_TOKEN:-}}" ]]; then
    echo "gh: To use GitHub CLI in a GitHub Actions workflow, set the GH_TOKEN environment variable." >&2
    exit 4
fi
echo "gh $*" >> "{log_file}"
case "$*" in
  *"pulls/"*"/reviews"*"-X PUT"*) echo '{{"id": 42}}' ;;
  *"pulls/"*"/reviews"*) echo '[{{"id": 42, "user": {{"login": "github-actions[bot]"}}, "body": "## Skill Eval Results\\nold"}}]' ;;
  *) echo "mock-gh-ok" ;;
esac
exit 0
''')
    mock_script.chmod(mock_script.stat().st_mode | stat.S_IEXEC)
    return str(mock_dir), str(log_file)


def _base_env(mock_dir):
    env = os.environ.copy()
    env["PATH"] = mock_dir + ":" + env["PATH"]
    env["GH_TOKEN"] = "test-token"
    return env


# --- auth validation ---

def test_pr_fails_without_token(mock_gh, tmp_path):
    mock_dir, _ = mock_gh
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "summary.md").write_text("# Results\nAll pass")
    env = os.environ.copy()
    env["PATH"] = mock_dir + ":" + env["PATH"]
    env["PR_NUMBER"] = "1"
    env.pop("GH_TOKEN", None)
    env.pop("GITHUB_TOKEN", None)

    result = subprocess.run(
        ["bash", SCRIPT, "pr", "--workspace", str(ws)],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0
    assert "GH_TOKEN" in result.stderr


# --- comment-reply subcommand ---

def test_comment_reply_rejects_non_numeric_id(mock_gh):
    mock_dir, _ = mock_gh
    env = _base_env(mock_dir)
    result = subprocess.run(
        ["bash", SCRIPT, "comment-reply", "--comment-id", "abc", "--reaction", "eyes"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0
    assert "invalid comment ID" in result.stderr


def test_comment_reply_accepts_numeric_id(mock_gh):
    mock_dir, _ = mock_gh
    env = _base_env(mock_dir)
    result = subprocess.run(
        ["bash", SCRIPT, "comment-reply", "--comment-id", "12345", "--reaction", "eyes"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0


def test_comment_reply_unknown_args(mock_gh):
    mock_dir, _ = mock_gh
    env = _base_env(mock_dir)
    result = subprocess.run(
        ["bash", SCRIPT, "comment-reply", "--unknown", "value"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0


def test_invalid_mode(mock_gh):
    mock_dir, _ = mock_gh
    env = _base_env(mock_dir)
    result = subprocess.run(
        ["bash", SCRIPT, "badmode"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0
    assert "Usage" in result.stderr


# --- pr subcommand ---

def test_pr_creates_new_review(mock_gh, tmp_path):
    mock_dir, log_file = mock_gh
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "summary.md").write_text("# Results\nAll pass")
    env = _base_env(mock_dir)
    env["PR_NUMBER"] = "42"

    result = subprocess.run(
        ["bash", SCRIPT, "pr", "--workspace", str(ws)],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "Posted new PR review" in result.stdout

    log = open(log_file).read()
    assert "pulls/42/reviews" in log
    assert "-X POST" in log


def test_pr_updates_existing_review(mock_gh_with_existing_review, tmp_path):
    mock_dir, log_file = mock_gh_with_existing_review
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "summary.md").write_text("# Results\nAll pass")
    env = _base_env(mock_dir)
    env["PR_NUMBER"] = "10"

    result = subprocess.run(
        ["bash", SCRIPT, "pr", "--workspace", str(ws)],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "Updated existing PR review" in result.stdout

    log = open(log_file).read()
    assert "-X PUT" in log


def test_pr_requires_workspace():
    env = os.environ.copy()
    env["GH_TOKEN"] = "test-token"
    result = subprocess.run(
        ["bash", SCRIPT, "pr"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0
    assert "--workspace required" in result.stderr


def test_pr_missing_pr_number(mock_gh, tmp_path):
    mock_dir, _ = mock_gh
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "summary.md").write_text("# Results\nAll pass")
    env = _base_env(mock_dir)
    env.pop("PR_NUMBER", None)

    result = subprocess.run(
        ["bash", SCRIPT, "pr", "--workspace", str(ws)],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0
    assert "could not detect valid PR number" in result.stderr


def test_pr_multiple_workspaces(mock_gh, tmp_path):
    mock_dir, log_file = mock_gh
    ws1 = tmp_path / "ws1"
    ws2 = tmp_path / "ws2"
    ws1.mkdir()
    ws2.mkdir()
    (ws1 / "summary.md").write_text("# Skill A\nPass")
    (ws2 / "summary.md").write_text("# Skill B\nPass")
    env = _base_env(mock_dir)
    env["PR_NUMBER"] = "7"

    result = subprocess.run(
        ["bash", SCRIPT, "pr",
         "--workspace", str(ws1), "--workspace", str(ws2)],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "Posted new PR review" in result.stdout
