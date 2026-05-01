"""Tests for post-results.sh comment-reply subcommand."""
import os
import stat
import subprocess

import pytest

SCRIPT = "plugins/skill-litmus/scripts/post-results.sh"


@pytest.fixture
def mock_gh(tmp_path):
    mock_dir = tmp_path / "mock-bin"
    mock_dir.mkdir()
    mock_script = mock_dir / "gh"
    mock_script.write_text('#!/usr/bin/env bash\necho "mock-gh-ok"')
    mock_script.chmod(mock_script.stat().st_mode | stat.S_IEXEC)
    return str(mock_dir)


def test_comment_reply_rejects_non_numeric_id(mock_gh):
    env = os.environ.copy()
    env["PATH"] = mock_gh + ":" + env["PATH"]
    result = subprocess.run(
        ["bash", SCRIPT, "comment-reply", "--comment-id", "abc", "--reaction", "eyes"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode != 0
    assert "invalid comment ID" in result.stderr


def test_comment_reply_accepts_numeric_id(mock_gh):
    env = os.environ.copy()
    env["PATH"] = mock_gh + ":" + env["PATH"]
    result = subprocess.run(
        ["bash", SCRIPT, "comment-reply", "--comment-id", "12345", "--reaction", "eyes"],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0


def test_comment_reply_unknown_args():
    result = subprocess.run(
        ["bash", SCRIPT, "comment-reply", "--unknown", "value"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0


def test_invalid_mode():
    result = subprocess.run(
        ["bash", SCRIPT, "badmode"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "Usage" in result.stderr
