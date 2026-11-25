import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from modal_receipts.manifest import baseline_hosts
from modal_receipts.plugin import RolloutEvidencePlugin
from modal_receipts.rollout import build_rollout_evidence


def frozen(directory, hosts, partial=False):
    directory.mkdir()
    evidence = build_rollout_evidence()
    evidence["frozen_at"] = "AGENT_END"
    evidence["details"]["network_capture"] = {
        "relayed_hosts": hosts,
        "partial": partial,
    }
    (directory / "rollout-evidence.json").write_text(json.dumps(evidence))
    return evidence


def test_baseline_union_uses_frozen_captures(tmp_path):
    frozen(tmp_path / "one", ["b.example", "a.example"])
    frozen(tmp_path / "two", ["a.example", "c.example"], partial=True)
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "rollout-evidence.json").write_text('{"relayed_hosts":["unfrozen.example"]}')
    assert baseline_hosts(tmp_path) == (["a.example", "b.example", "c.example"], 2, 1)
    with pytest.raises(ValueError, match="No frozen"):
        baseline_hosts(bad)


async def test_job_end_manifest_hashes_frozen_and_marks_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("GARNET_RECORDER_COMMIT", "test-commit")
    good = tmp_path / "trial-1"
    evidence = frozen(good, ["a.example"])
    evidence["checks"]["off_policy_host"]["state"] = "observed"
    (good / "rollout-evidence.json").write_text(json.dumps(evidence))
    raw = b'{"capture":"raw"}\n'
    (good / "guest-capture.json").write_bytes(raw)
    plugin = RolloutEvidencePlugin()
    await plugin.on_job_start(Mock(job_dir=tmp_path))
    await plugin.on_job_end(
        SimpleNamespace(
            trial_results=[
                SimpleNamespace(trial_name="trial-2", task_name="missing"),
                SimpleNamespace(trial_name="trial-1", task_name="observed"),
            ]
        )
    )
    manifest = json.loads((tmp_path / "integrity-manifest.json").read_text())
    assert manifest["recorder"]["commit"] == "test-commit"
    assert manifest["recorder"]["version"]
    observed, missing = manifest["trials"]
    assert (
        observed["artifact_sha256"]["trial-1/guest-capture.json"]
        == hashlib.sha256(raw).hexdigest()
    )
    assert observed["artifact_sha256"]["trial-1/sidecar-capture.json"] is None
    assert observed["verdict"] == "observed" and observed["coverage_incomplete"]
    assert missing["verdict"] == "unknown" and missing["coverage_incomplete"]
    assert "Unknown is not clean." in (tmp_path / "integrity-manifest.md").read_text()
