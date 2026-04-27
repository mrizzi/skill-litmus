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
