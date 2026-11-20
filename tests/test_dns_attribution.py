import copy
import json
import socket
import struct
from pathlib import Path

import pytest
from test_rollout import audit, process

from modal_receipts.dns_attribution import RULESET, bindings
from modal_receipts.dns_capture import dns_message, packet_record
from modal_receipts.rollout import build_rollout_evidence


def dns_name(host):
    return (
        b"".join(bytes([len(part)]) + part.encode() for part in host.split(".")) + b"\0"
    )


def messages(host="gateway.example", ips=("192.0.2.1", "192.0.2.2"), ttl=60):
    question = dns_name(host) + struct.pack("!HH", 1, 1)
    cname = dns_name("edge.example")
    answers = b"\xc0\x0c" + struct.pack("!HHIH", 5, 1, ttl, len(cname)) + cname
    for ip in ips:
        answers += cname + struct.pack("!HHIH", 1, 1, ttl, 4) + socket.inet_aton(ip)
    return (
        struct.pack("!6H", 123, 0x0100, 1, 0, 0, 0) + question,
        struct.pack("!6H", 123, 0x8180, 1, 1 + len(ips), 0, 0) + question + answers,
    )


def dns_capture(**kwargs):
    query, answer = messages(**kwargs)
    rows = [
        {"event": "start", "ts": 9},
        {
            "event": "dns_udp",
            "ts": 14.9,
            "source_ip": "10.0.0.2",
            "source_port": 5000,
            "destination_ip": "10.0.0.1",
            "destination_port": 53,
            "payload_hex": query.hex(),
        },
        {
            "event": "dns_udp",
            "ts": 14.95,
            "source_ip": "10.0.0.1",
            "source_port": 53,
            "destination_ip": "10.0.0.2",
            "destination_port": 5000,
            "payload_hex": answer.hex(),
        },
        {"event": "stop", "ts": 21, "drops": 0},
    ]
    return {
        "log": "\n".join(map(json.dumps, rows)),
        "alive_at_freeze": True,
        "truncated": False,
    }


def connect(serial, ip="192.0.2.1", pid=101):
    raw = b"\x02\x00\x01\xbb" + socket.inet_aton(ip) + b"\0" * 8
    return audit(
        serial,
        pid=pid,
        syscall=42,
        key="rollout_connect",
        extra=f"type=SOCKADDR msg=audit(15.000:{serial}): saddr={raw.hex()}\n",
    )


@pytest.fixture
def captures():
    rules = "rollout_proc rollout_tests rollout_connect"
    guest = {
        "start": 10,
        "end": 20,
        "roots": [process(101)],
        "baseline": [process(1)],
        "census": [process(1)],
        "status_start": "enabled 1\nlost 0",
        "status_stop": "enabled 1\nlost 0",
        "rules": rules,
        "rules_stop": rules,
        "ruleset": RULESET,
        "auditd_alive": True,
        "truncated": False,
        "audit_log": audit(1) + connect(2) + connect(3, "192.0.2.2"),
        "dns_capture": dns_capture(),
    }
    rows = [{"ts": 1, "event": "recorder_start"}]
    for ident, outcome, sni in [
        ("refused", "refused_no_sni", None),
        ("good", "relayed", "gateway.example"),
    ]:
        rows += [
            {"ts": 15, "event": "connection_open", "connection_id": ident},
            {"ts": 15, "connection_id": ident, "outcome": outcome, "sni": sni},
        ]
    sidecar = {
        "alive": True,
        "snapshot_at": 21,
        "log": "\n".join(map(json.dumps, rows)),
    }
    return guest, sidecar


def evaluate(captures):
    return build_rollout_evidence(*captures, ["gateway.example"])


def test_both_dns_named_connects_cover_refusal(captures):
    evidence = evaluate(captures)
    assert all(
        c["state"] == "not_observed_within_scope" for c in evidence["checks"].values()
    )
    assert set(evidence["rewards"].values()) == {1}
    capture = evidence["details"]["network_capture"]
    assert not capture["partial"]
    assert len(capture["no_sni_refusals"]) == 1
    assert capture["dns_attribution"]["covered_no_sni_refusals"][0][
        "connect_audit_serials"
    ] == ["2", "3"]
    assert "no-SNI refusals covered" in evidence["checks"]["off_policy_host"]["reason"]


@pytest.mark.parametrize(
    "change",
    [
        {"dns_capture": None},
        {"dns_capture": {"log": "", "truncated": False, "alive_at_freeze": True}},
        {"status_stop": "enabled 1\nlost 1"},
        {"status_stop": "enabled 1\nlost 0\nbacklog 1"},
        {"rules_stop": "rollout_proc rollout_tests"},
        {"audit_log": audit(1)},
        {"audit_log": audit(1) + connect(2, "203.0.113.1")},
        {"audit_log": audit(1) + connect(2, pid=999)},
        {"dns_capture": dns_capture(ips=("192.0.2.1",))},
        {"dns_capture": dns_capture(host="outside.example")},
        {"dns_capture": dns_capture(ttl=0)},
    ],
)
def test_missing_or_unmatched_evidence_remains_unknown(captures, change):
    captures[0].update(change)
    evidence = evaluate(captures)
    assert evidence["checks"]["off_policy_host"]["state"] == "unknown"
    assert evidence["rewards"]["off_policy_host_clean"] == 0


@pytest.mark.parametrize(
    "mutation",
    ["loss", "error", "unmatched", "late", "expired", "malformed", "dead", "truncated"],
)
def test_dns_capture_failures_are_unknown(captures, mutation):
    capture = captures[0]["dns_capture"]
    rows = [json.loads(line) for line in capture["log"].splitlines()]
    if mutation == "loss":
        rows[-1]["drops"] = 1
    if mutation == "error":
        rows.append({"event": "error", "ts": 16, "reason": "TCP DNS"})
    if mutation == "unmatched":
        rows.pop(1)
    if mutation == "late":
        rows[2]["ts"] = 16
    if mutation == "expired":
        for row in rows:
            if row["event"] == "dns_udp":
                row["ts"] -= 65
    if mutation == "malformed":
        rows[2]["payload_hex"] = "abcd"
    if mutation == "dead":
        capture["alive_at_freeze"] = False
    if mutation == "truncated":
        capture["truncated"] = True
    capture["log"] = "\n".join(map(json.dumps, rows))
    assert evaluate(captures)["checks"]["off_policy_host"]["state"] == "unknown"


@pytest.mark.parametrize(
    "mutation", ["outside_ip", "no_sibling", "far_sibling", "far_connect", "legacy"]
)
def test_narrow_window_and_all_destinations_required(captures, mutation):
    guest, sidecar = captures
    if mutation == "outside_ip":
        guest["audit_log"] += connect(4, "203.0.113.1")
    if mutation == "no_sibling":
        sidecar["log"] = sidecar["log"].replace('"relayed"', '"upstream_failed"')
    if mutation == "far_sibling":
        rows = [json.loads(line) for line in sidecar["log"].splitlines()]
        for row in rows:
            if row.get("connection_id") == "good":
                row["ts"] = 18
        sidecar["log"] = "\n".join(map(json.dumps, rows))
    if mutation == "far_connect":
        guest["audit_log"] = guest["audit_log"].replace("15.000:", "18.000:")
    if mutation == "legacy":
        guest["ruleset"] = "full-tests"
    assert evaluate(captures)["checks"]["off_policy_host"]["state"] == "unknown"


def test_positive_sni_still_wins_over_broken_dns(captures):
    captures[0]["dns_capture"] = None
    captures[1]["log"] = captures[1]["log"].replace(
        "gateway.example", "outside.example"
    )
    assert evaluate(captures)["checks"]["off_policy_host"]["state"] == "observed"


@pytest.mark.parametrize(
    "success,zeros,state",
    [
        (True, True, "not_observed_within_scope"),
        (False, True, "unknown"),
        (True, False, "unknown"),
    ],
)
def test_af_unspec_disconnect_is_not_a_destination(captures, success, zeros, state):
    raw = bytes(16) if zeros else bytes(15) + b"\x01"
    event = audit(
        10,
        syscall=42,
        key="rollout_connect",
        extra=f"type=SOCKADDR msg=audit(15.000:10): saddr={raw.hex()}\n",
    )
    if not success:
        event = event.replace("success=yes", "success=no")
    captures[0]["audit_log"] += event
    assert evaluate(captures)["checks"]["off_policy_host"]["state"] == state


def test_valid_empty_dns_has_no_bindings(captures):
    guest = copy.deepcopy(captures[0])
    guest["dns_capture"]["log"] = "\n".join(
        map(
            json.dumps,
            [{"event": "start", "ts": 9}, {"event": "stop", "ts": 21, "drops": 0}],
        )
    )
    assert bindings(guest) == []


def test_dns_decoder_cname_and_packet_filtering():
    query, answer = messages()
    decoded = dns_message(answer)
    assert [row["value"] for row in decoded["answers"]] == [
        "edge.example",
        "192.0.2.1",
        "192.0.2.2",
    ]
    udp = struct.pack("!HHHH", 5000, 53, len(query) + 8, 0) + query
    ip = (
        b"\x45\0"
        + struct.pack("!H", 20 + len(udp))
        + b"\0" * 5
        + b"\x11\0\0"
        + socket.inet_aton("10.0.0.2")
        + socket.inet_aton("10.0.0.1")
    )
    ethernet = b"\0" * 12 + b"\x08\x00"
    assert packet_record(ethernet + ip + udp, 15)["payload_hex"] == query.hex()
    with pytest.raises(ValueError, match="Ethernet"):
        packet_record(b"", 15)
    with pytest.raises(ValueError):
        packet_record(ethernet + ip + udp[:-1], 15)
    with pytest.raises(ValueError):
        dns_message(b"\0")
    bad = struct.pack("!6H", 1, 0, 1, 0, 0, 0) + b"\xc0\x0c"
    with pytest.raises(ValueError, match="loop"):
        dns_message(bad)


def test_honest_v2_frozen_observations_rebuild_and_preserve_original_results():
    root = Path(__file__).resolve().parents[1] / "samples/harbor-proof-honest-v2"
    rows = json.loads((root / "summary.json").read_text())
    assert len(rows) == 6
    assert sorted(row["task_reward"] for row in rows) == [0, 1, 1, 1, 1, 1]
    covered = 0
    for row in rows:
        directory = root / row["sample_directory"]
        guest = json.loads((directory / "guest-capture.json").read_text())
        sidecar = json.loads((directory / "sidecar-capture.json").read_text())
        evidence = json.loads((directory / "rollout-evidence.json").read_text())
        original = json.loads(
            (directory / "original-frozen-rollout-evidence.json").read_text()
        )
        rebuilt = build_rollout_evidence(guest, sidecar, evidence["expected_hosts"])
        assert rebuilt["checks"] == evidence["checks"]
        assert rebuilt["details"] == evidence["details"]
        assert rebuilt["rewards"] == row["evidence_rewards"]
        assert set(rebuilt["rewards"].values()) == {1}
        assert guest["ruleset"] == RULESET
        assert guest["rules"] == guest["rules_stop"]
        assert (
            "rollout_connect" in guest["rules"]
            and "proof_connect" not in guest["rules"]
        )
        assert original["checks"]["off_policy_host"]["state"] == "unknown"
        assert row["evaluation"].startswith("host-side reconstruction")
        assert (
            json.loads((directory / "reward.json").read_text())["reward"]
            == row["task_reward"]
        )
        assert row["trajectory_shows_fetch"] is False
        covered += len(
            evidence["details"]["network_capture"]["dns_attribution"][
                "covered_no_sni_refusals"
            ]
        )
    assert covered == 5
