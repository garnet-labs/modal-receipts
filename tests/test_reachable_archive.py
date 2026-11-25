import json
import subprocess
import sys
from pathlib import Path


def test_archived_trajectories_reproduce_published_labels(tmp_path):
    runs = Path(__file__).resolve().parents[1] / "samples/harbor-tb2-reachable/runs"
    generated = subprocess.check_output(
        [sys.executable, str(runs / "label.py")], cwd=tmp_path
    )
    assert json.loads(generated) == json.loads((runs / "labels.json").read_text())
