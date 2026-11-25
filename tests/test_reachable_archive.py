import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest


def test_rebuilding_task_variants_requires_cached_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    generator = Path(__file__).resolve().parents[1] / "examples/prepare_tb2_reachable.py"

    with pytest.raises(SystemExit, match=r"regex-log.*Harbor task cache at") as exc:
        runpy.run_path(str(generator), run_name="__main__")

    assert str(tmp_path / ".cache/harbor/tasks") in str(exc.value)


def test_archived_trajectories_reproduce_published_labels(tmp_path):
    runs = Path(__file__).resolve().parents[1] / "samples/harbor-tb2-reachable/runs"
    generated = subprocess.check_output(
        [sys.executable, str(runs / "label.py")], cwd=tmp_path
    )
    assert json.loads(generated) == json.loads((runs / "labels.json").read_text())
