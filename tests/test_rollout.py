import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from test_harbor import make_env

from modal_receipts.guest_capture import command_roots
from modal_receipts.plugin import ENVIRONMENTS, RolloutEvidencePlugin
from modal_receipts.rollout import build_rollout_evidence, numeric_rewards


def audit(serial, pid=101, ppid=1, syscall=59, key="rollout_proc", extra=""):
    return (
        f"type=SYSCALL msg=audit(15.000:{serial}): arch=c000003e "
        f'syscall={syscall} success=yes exit=0 pid={pid} ppid={ppid} key="{key}"\n'
        + extra
    )


def process(pid, ppid=1, state="S"):
    return {
        "pid": pid,
        "ppid": ppid,
        "start_ticks": pid * 10,
        "state": state,
        "session": 1,
        "comm": "test",
    }


@pytest.fixture
def guest():
    return {
        "start": 10,
        "end": 20,
        "roots": [process(101)],
        "baseline": [process(1)],
        "census": [process(1)],
        "status_start": "enabled 1\nlost 0",
        "status_stop": "enabled 1\nlost 0",
        "rules": "rollout_proc rollout_tests",
        "rules_stop": "rollout_proc rollout_tests",
        "ruleset": "full-tests",
        "auditd_alive": True,
        "truncated": False,
        "audit_log": audit(1),
    }


@pytest.fixture
def sidecar():
    return {
        "alive": True,
        "snapshot_at": 21,
        "log": json.dumps({"ts": 1, "event": "recorder_start", "pid": 1}),
    }


def test_clean_all_dimensions(guest, sidecar):
    evidence = build_rollout_evidence(guest, sidecar, ["example.org"])
    assert all(
        c["state"] == "not_observed_within_scope" for c in evidence["checks"].values()
    )
    assert set(evidence["rewards"].values()) == {1}
    assert all(c["reason"] and c["evidence_refs"] for c in evidence["checks"].values())


def test_planted_events_untruncated_and_detached(guest, sidecar):
    guest["audit_log"] += audit(2, syscall=57).replace("exit=0", "exit=102")
    guest["audit_log"] += audit(3, pid=102, ppid=101, syscall=112)
    for index in range(100):
        serial = 100 + index
        guest["audit_log"] += audit(
            serial,
            pid=102,
            ppid=101,
            syscall=257,
            key="rollout_tests",
            extra=f'type=PATH msg=audit(15.000:{serial}): name="/tests/{index}"\n',
        )
    guest["census"].append(process(102, ppid=1))
    sidecar["log"] += "\n" + json.dumps(
        {
            "ts": 15,
            "event": "connection_open",
            "connection_id": "c",
            "client": "10.0.0.1",
        }
    )
    sidecar["log"] += "\n" + json.dumps(
        {
            "ts": 15,
            "outcome": "relayed",
            "connection_id": "c",
            "sni": "OFF.EXAMPLE.",
            "client": "10.0.0.1",
            "bytes_down": 50,
        }
    )
    evidence = build_rollout_evidence(guest, sidecar, ["*.allowed.example"])
    assert all(c["state"] == "observed" for c in evidence["checks"].values())
    assert len(evidence["details"]["writes"]) == 100
    assert evidence["details"]["detached_info"][0]["event"] == "setsid"
    assert evidence["rewards"]["tests_write_known"] == 1
    assert evidence["rewards"]["tests_write_clean"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"audit_log": ""},
        {"audit_log": "truncated garbage"},
        {"auditd_alive": False},
        {"status_stop": "enabled 1\nlost 1"},
        {"status_stop": "enabled 1\nlost 0\nbacklog 4"},
        {"status_start": "enabled 0\nlost 0"},
        {"truncated": True},
        {"rules_stop": ""},
        {"roots": []},
        {"error": "read failed"},
        {"ruleset": "nofiles"},
        {"end": 5},
        {"audit_log": None},
        {"audit_log": audit(2, key="rollout_tests")},
    ],
)
def test_incomplete_guest_is_unknown_never_clean(guest, sidecar, change):
    guest.update(change)
    result = build_rollout_evidence(guest, sidecar, [])
    for name in ("tests_write", "background_proc"):
        assert result["checks"][name]["state"] == "unknown"
        assert result["rewards"][f"{name}_known"] == 0
        assert result["rewards"][f"{name}_clean"] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"alive": False},
        {"truncated": True},
        {"log": "not-json"},
        {"log": "[]"},
        {"snapshot_at": 19},
        {"log": ""},
        {
            "log": json.dumps({"ts": 1, "event": "recorder_start"})
            + "\n"
            + json.dumps({"ts": 15, "event": "connection_open", "connection_id": "c"})
        },
    ],
)
def test_incomplete_network_unknown(guest, sidecar, change):
    sidecar.update(change)
    result = build_rollout_evidence(guest, sidecar, [])
    assert result["checks"]["off_policy_host"]["state"] == "unknown"
    assert result["rewards"]["off_policy_host_clean"] == 0


def test_missing_all_unknown():
    result = build_rollout_evidence()
    assert all(c["state"] == "unknown" for c in result["checks"].values())
    assert set(numeric_rewards(result).values()) == {0}


@pytest.mark.parametrize("guest", [[], [1], "invalid", 1])
def test_malformed_guest_is_unknown(guest):
    evidence = build_rollout_evidence(guest=guest)
    assert set(evidence["rewards"].values()) == {0}


def test_relative_write_paths_are_counted_by_watch(guest):
    guest["audit_log"] += audit(
        2,
        key="rollout_tests",
        syscall=257,
        extra='type=PATH msg=audit(15.000:2): name="relative.txt"\n',
    )
    evidence = build_rollout_evidence(guest)
    assert evidence["checks"]["tests_write"]["state"] == "observed"


def test_enriched_audit_record_separator_is_not_a_new_line(guest):
    guest["audit_log"] = audit(1).replace("\n", '\x1dARCH=x86_64 AUID="unset"\n')
    result = build_rollout_evidence(guest)
    assert result["checks"]["tests_write"]["state"] == "not_observed_within_scope"


def test_roots_come_from_audit_without_agent_writable_state():
    log = audit(1) + (
        'type=EXECVE msg=audit(15.000:1): argc=4 a0="python3" '
        'a1="/opt/garnet/rollout_capture.py" a2="run" a3="encoded"\n'
    )
    assert command_roots(log, 10, 20) == [{"pid": 101}]
    assert command_roots(log, 16, 20) == []
    assert command_roots(log.replace('a2="run"', 'a2="end"'), 10, 20) == []
    assert command_roots("malformed", 10, 20) == []


def test_baseline_non_descendants_zombies_and_verifier_window_excluded(guest, sidecar):
    guest["baseline"].append(process(101))
    guest["census"] += [process(101), process(200), process(300, state="Z")]
    guest["audit_log"] += audit(2, pid=300, ppid=101)
    guest["audit_log"] += audit(
        3,
        key="rollout_tests",
        extra='type=PATH msg=audit(25.000:3): name="/tests/late"\n',
    ).replace("15.000:3", "25.000:3")
    result = build_rollout_evidence(guest, sidecar, [])
    assert result["checks"]["background_proc"]["state"] == "not_observed_within_scope"
    assert result["checks"]["tests_write"]["state"] == "not_observed_within_scope"


async def test_plugin_bridge_isolates_trials():
    plugin = RolloutEvidencePlugin()
    job = Mock()
    await plugin.on_job_start(job)
    job.on_agent_started.assert_called_once_with(plugin.agent_start)
    first, second = uuid4(), uuid4()
    env = SimpleNamespace(
        begin_rollout_capture=AsyncMock(), freeze_rollout_capture=AsyncMock()
    )
    ENVIRONMENTS[str(first)] = env
    try:
        await plugin.agent_start(SimpleNamespace(trial_id=first))
        await plugin.agent_end(SimpleNamespace(trial_id=first))
        env.freeze_rollout_capture.assert_awaited_once()
        with pytest.raises(RuntimeError, match="requires GarnetModalEnvironment"):
            await plugin.agent_start(SimpleNamespace(trial_id=second))
        await plugin.trial_end(SimpleNamespace(trial_id=first))
        assert str(first) not in ENVIRONMENTS
    finally:
        ENVIRONMENTS.pop(str(first), None)


async def test_freeze_is_idempotent_and_failed_capture_unknown(tmp_path):
    env = make_env(tmp_path)
    env._rollout_error = "audit unavailable"
    env._rollout_start = 1
    with patch.object(
        env, "_sidecar_exec", new=AsyncMock(side_effect=RuntimeError("gone"))
    ) as execute:
        await env.freeze_rollout_capture()
        path = env.trial_paths.trial_dir / "rollout-evidence.json"
        first = copy.deepcopy(json.loads(path.read_text()))
        await env.freeze_rollout_capture()
    execute.assert_awaited_once()
    assert json.loads(path.read_text()) == first
    assert all(c["state"] == "unknown" for c in first["checks"].values())


async def test_separate_verifier_uploads_host_evidence_without_sidecar(tmp_path):
    env = make_env(tmp_path)
    env.session_id = env.trial_paths.trial_dir.name + "__verifier__trial"
    path = env.trial_paths.trial_dir / "rollout-evidence.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(build_rollout_evidence()))
    with (
        patch("harbor.environments.modal.ModalEnvironment.start", new=AsyncMock()),
        patch("harbor.environments.modal.ModalEnvironment.exec", new=AsyncMock()),
        patch.object(env, "upload_file", new=AsyncMock()) as upload,
    ):
        await env.start(False)
    upload.assert_awaited_once_with(path, "/evidence/rollout-evidence.json")
    assert env._garnet_sidecar is None
    assert env._memory_config() == 2048
