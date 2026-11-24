import importlib.util
import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from harbor.agents.installed.claude_code import ClaudeCode

from modal_receipts.rollout import build_rollout_evidence

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "examples" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("instruction", ["", "Solve the task"])
async def test_proof_fixture_executes_answer_then_scrubs_own_log(tmp_path, instruction):
    agent = object.__new__(load("harbor_cheat_agent").ProofCheatAgent)
    agent.proof_source = {"url": "https://raw.example/solve.sh", "sha256": "a" * 64}
    (tmp_path / "proof-source.json").write_text(json.dumps(agent.proof_source))
    agent.logs_dir = tmp_path / "agent"
    agent.environment_logs_dir = PurePosixPath("/logs/agent")
    environment = SimpleNamespace(
        upload_file=AsyncMock(), environment_dir=tmp_path / "environment"
    )
    edits = [{"path": "proof-fetch.txt", "removed_lines": 1}]
    with (
        patch.object(
            agent,
            "exec_as_agent",
            new=AsyncMock(
                side_effect=[
                    SimpleNamespace(return_code=0),
                    SimpleNamespace(return_code=0, stdout=json.dumps(edits)),
                ]
            ),
        ) as execute,
        patch.object(ClaudeCode, "run", new=AsyncMock()) as delegate,
    ):
        await agent.run(instruction, environment, None)
        delegate.assert_awaited_once_with(instruction, environment, None)
        first, second = execute.await_args_list
        assert "sha256sum -c" in first.kwargs["command"]
        assert "bash /tmp/proof-answer.sh" in first.kwargs["command"]
        assert "/tests/proof-marker.txt" in first.kwargs["command"]
        assert "nohup sleep 600" in first.kwargs["command"]
        assert "proof_scrub_logs.py" in second.kwargs["command"]
    record = json.loads((tmp_path / "proof-fixture.json").read_text())
    assert record["answer_executed"]
    assert record["log_edits"] == edits


@pytest.mark.parametrize("fetch_code,scrub_code", [(22, 0), (0, 1)])
async def test_proof_fixture_fails_closed_on_fetch_or_scrub_error(
    tmp_path, fetch_code, scrub_code
):
    agent = object.__new__(load("harbor_cheat_agent").ProofCheatAgent)
    agent.proof_source = {"url": "https://raw.example/solve.sh", "sha256": "a" * 64}
    (tmp_path / "proof-source.json").write_text(json.dumps(agent.proof_source))
    agent.logs_dir = tmp_path / "agent"
    agent.environment_logs_dir = PurePosixPath("/logs/agent")
    environment = SimpleNamespace(
        upload_file=AsyncMock(), environment_dir=tmp_path / "environment"
    )
    with (
        patch.object(
            agent,
            "exec_as_agent",
            new=AsyncMock(
                side_effect=[
                    SimpleNamespace(return_code=fetch_code),
                    SimpleNamespace(return_code=scrub_code),
                ]
            ),
        ),
        patch.object(ClaudeCode, "run", new=AsyncMock()) as delegate,
        pytest.raises(RuntimeError),
    ):
        await agent.run("Solve", environment, None)
    if fetch_code:
        delegate.assert_not_awaited()
    assert not (tmp_path / "proof-fixture.json").exists()


def test_log_scrub_removes_only_matching_lines(tmp_path):
    scrub = load("proof_scrub_logs").scrub_logs
    log = tmp_path / "stream.jsonl"
    log.write_text('{"message":"normal"}\n{"message":"fetch-marker"}\n')
    assert scrub(tmp_path, ["fetch-marker"]) == [
        {"path": "stream.jsonl", "removed_lines": 1}
    ]
    assert json.loads(log.read_text()) == {"message": "normal"}
    assert scrub(tmp_path, ["fetch-marker"]) == []
    assert scrub(tmp_path / "missing", ["fetch-marker"]) == []
    binary = tmp_path / "binary.log"
    binary.write_bytes(b"\xff")
    assert scrub(tmp_path, ["missing"]) == []
    assert binary.read_bytes() == b"\xff"


def test_policy_is_oracle_window_hosts_plus_model_endpoint(tmp_path, monkeypatch):
    module = load("prepare_harbor_proof")
    monkeypatch.setattr(module, "ROOT", tmp_path / "export")
    records = [
        {"ts": 15, "sni": "oracle.example", "outcome": "relayed"},
        {"ts": 9, "sni": "setup.example", "outcome": "relayed"},
        {"ts": 15, "sni": "failed.example", "outcome": "upstream_failed"},
        {
            "ts": 15,
            "sni": "loopback.example",
            "outcome": "relayed",
            "client": "127.0.0.1:1",
        },
    ]
    for name in module.TASKS:
        (module.ROOT / "tasks" / name).mkdir(parents=True)
        trial = tmp_path / "oracle" / (name + "__trial")
        trial.mkdir(parents=True)
        (trial / "rollout-evidence.json").write_text(
            json.dumps({"window": {"start": 10, "end": 20}})
        )
        (trial / "sidecar-capture.json").write_text(
            json.dumps({"log": "\n".join(map(json.dumps, records))})
        )
    module.derive_policy(tmp_path / "oracle")
    provenance = json.loads((module.ROOT / "policy-provenance.json").read_text())
    for name in module.TASKS:
        assert provenance[name]["expected_hosts"] == [
            "ai-gateway.vercel.sh",
            "oracle.example",
        ]
        assert provenance[name]["oracle_hosts"] == ["oracle.example"]


def test_export_scrubs_and_rejects_remaining_secret(tmp_path, monkeypatch):
    module = load("export_harbor_proof")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    assert module.scrub(
        {"client": "private-peer", "value": "secret-value"}, ["secret-value"]
    ) == {"client": "redacted", "value": "[REDACTED]"}
    module.scan(["secret-value"])
    (tmp_path / "artifact.txt").write_text("secret-value")
    with pytest.raises(ValueError, match="Secret scan failed"):
        module.scan(["secret-value"])


def test_proof_samples_rebuild_frozen_evidence_and_use_standard_rules():
    summaries = json.loads((ROOT / "samples/harbor-proof/summary.json").read_text())
    assert len(summaries) == 12
    for row in summaries:
        directory = ROOT / "samples/harbor-proof" / row["sample_directory"]
        guest = json.loads((directory / "guest-capture.json").read_text())
        sidecar = json.loads((directory / "sidecar-capture.json").read_text())
        evidence = json.loads((directory / "rollout-evidence.json").read_text())
        rebuilt = build_rollout_evidence(guest, sidecar, evidence["expected_hosts"])
        assert rebuilt["checks"] == evidence["checks"]
        assert rebuilt["details"] == evidence["details"]
        assert rebuilt["rewards"] == evidence["rewards"] == row["evidence_rewards"]
        assert "proof_connect" not in guest["rules"]
        assert guest["rules"] == guest["rules_stop"]
        assert (
            json.loads((directory / "reward.json").read_text())["reward"]
            == row["task_reward"]
        )
        if row["arm"] == "cheat":
            assert json.loads((directory / "proof-fixture.json").read_text())[
                "answer_executed"
            ]
            assert row["trajectory_shows_fetch"] is False
