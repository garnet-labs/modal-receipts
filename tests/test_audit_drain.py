from unittest.mock import Mock

import pytest
import test_rollout

from modal_receipts import guest_capture
from modal_receipts.rollout import build_rollout_evidence


def status(backlog, lost=0):
    return f"enabled 1\nbacklog {backlog}\nlost {lost}\n"


@pytest.mark.parametrize(
    "statuses,flushed,complete,timed_out",
    [
        ([status(50000), status(100), status(0)], True, True, False),
        ([status(50000), status(100), status(100)], True, False, True),
        ([status(50000), status(0, 1)], True, False, False),
        ([status(0), status(0), status(0)], False, False, True),
    ],
)
def test_drain_loop(monkeypatch, statuses, flushed, complete, timed_out):
    guest = test_rollout.guest.__wrapped__()
    sidecar = test_rollout.sidecar.__wrapped__()
    readings = iter(statuses)
    commands = []

    def command(*args):
        commands.append(args)
        return next(readings) if args == ("auditctl", "-s") else ""

    monkeypatch.setattr(guest_capture, "command", command)
    monkeypatch.setattr(guest_capture, "audit_flushed", Mock(return_value=flushed))
    monkeypatch.setattr(guest_capture.time, "sleep", lambda _: None)
    monkeypatch.setattr(guest_capture.time, "monotonic", Mock(side_effect=[0, 0, 1]))
    result = guest_capture.drain_audit(timeout=1)
    assert result["complete"] is complete
    assert result["timed_out"] is timed_out
    assert result["backlog_before"] == int(statuses[0].splitlines()[1].split()[1])
    assert commands[1][:2] == ("auditctl", "-m")
    guest["status_stop"] = result["status_at_freeze"]
    guest["truncated"] = not result["complete"]
    evidence = build_rollout_evidence(guest, sidecar, ["allowed.example"])
    expected = "not_observed_within_scope" if complete else "unknown"
    assert evidence["checks"]["tests_write"]["state"] == expected
    assert evidence["checks"]["background_proc"]["state"] == expected


def test_flush_requires_marker_and_fsync(monkeypatch, tmp_path):
    log = tmp_path / "audit.log"
    log.write_bytes(b"unrelated")
    monkeypatch.setattr(guest_capture, "AUDIT", log)
    fsync = Mock()
    monkeypatch.setattr(guest_capture.os, "fsync", fsync)
    assert not guest_capture.audit_flushed("marker")
    fsync.assert_not_called()
    log.write_bytes(b"prefix marker suffix")
    assert guest_capture.audit_flushed("marker")
    fsync.assert_called_once()
