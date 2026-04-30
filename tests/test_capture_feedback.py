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


def test_missing_output_arg():
    result = subprocess.run(
        ["bash", SCRIPT, "--eval", "1", "text"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "output" in result.stderr.lower()


def test_no_feedback_entries(tmp_path):
    output = tmp_path / "feedback.json"
    result = subprocess.run(
        ["bash", SCRIPT, "--output", str(output)],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "no feedback" in result.stderr.lower()
