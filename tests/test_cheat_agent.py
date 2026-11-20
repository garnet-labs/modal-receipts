import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from harbor.agents.installed.claude_code import ClaudeCode

from modal_receipts.rollout import build_rollout_evidence

spec = importlib.util.spec_from_file_location(
    "harbor_cheat_agent",
    Path(__file__).resolve().parents[1] / "examples" / "harbor_cheat_agent.py",
)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


@pytest.mark.parametrize("return_code", [0, 22])
async def test_fixture_fetches_then_delegates_only_on_success(return_code):
    agent = object.__new__(fixture.PlantedCheatAgent)
    environment, context = object(), object()
    with (
        patch.object(
            agent,
            "exec_as_agent",
            new=AsyncMock(return_value=SimpleNamespace(return_code=return_code)),
        ) as execute,
        patch.object(ClaudeCode, "run", new=AsyncMock()) as delegate,
    ):
        if return_code:
            with pytest.raises(RuntimeError, match="could not fetch"):
                await agent.run("Write done", environment, context)
            delegate.assert_not_awaited()
        else:
            await agent.run("Write done", environment, context)
            instruction, actual_environment, actual_context = delegate.await_args.args
            assert instruction.startswith("Write done")
            assert "/app/off-policy-reference.html" in instruction
            assert (actual_environment, actual_context) == (environment, context)
        execute.assert_awaited_once()
        assert "https://example.com" in execute.await_args.kwargs["command"]


@pytest.mark.parametrize("name", ["honest", "cheat"])
def test_scrubbed_paired_samples_reproduce_frozen_checks(name):
    directory = (
        Path(__file__).resolve().parents[1] / "samples" / "harbor-paired-v2" / name
    )
    evidence = json.loads((directory / "rollout-evidence.json").read_text())
    rebuilt = build_rollout_evidence(
        json.loads((directory / "guest-capture.json").read_text()),
        json.loads((directory / "sidecar-capture.json").read_text()),
        evidence["expected_hosts"],
    )
    assert rebuilt["checks"] == evidence["checks"]
    assert rebuilt["details"] == evidence["details"]
    assert rebuilt["rewards"] == json.loads((directory / "reward.json").read_text())
    trajectory = json.loads((directory / "trajectory.json").read_text())
    assert trajectory["schema_version"].startswith("ATIF-")
    assert trajectory["steps"][-1]["message"] in (directory / "CASE.md").read_text()
