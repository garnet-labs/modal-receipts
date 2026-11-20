"""Fail-closed DNS-set attribution for otherwise unnameable Sidecar refusals."""

import ipaddress
import json
from fnmatch import fnmatchcase

from modal_receipts.dns_capture import dns_message

RULESET = "full-tests-dns-v1"
TIME_TOLERANCE = 0.1


def allowed(host, expected):
    return any(
        fnmatchcase(host.lower().rstrip("."), p.lower().rstrip(".")) for p in expected
    )


def descendants(events, roots):
    found = {int(p["pid"]) for p in roots}
    edges = []
    for rows in events.values():
        for call in rows:
            if (
                call.get("type") != "SYSCALL"
                or call.get("key") != "rollout_proc"
                or call.get("success") != "yes"
            ):
                continue
            pid = int(call["pid"])
            edges.append((int(call["ppid"]), pid))
            if int(call["syscall"]) in (56, 57, 58, 435) and int(call["exit"]) > 0:
                edges.append((pid, int(call["exit"])))
    while True:
        children = {child for parent, child in edges if parent in found}
        if children <= found:
            return found
        found |= children


def bindings(guest):
    capture = guest["dns_capture"]
    if (
        capture.get("alive_at_freeze") is not True
        or capture.get("truncated") is not False
    ):
        raise ValueError("DNS collector missing, dead or truncated")
    rows = [json.loads(line) for line in capture["log"].splitlines()]
    starts = [r for r in rows if r["event"] == "start"]
    stops = [r for r in rows if r["event"] == "stop"]
    if (
        len(starts) != 1
        or starts[0]["ts"] > guest["start"]
        or len(stops) != 1
        or stops[0]["ts"] < guest["end"]
        or stops[0].get("drops") != 0
        or any(r["event"] not in ("start", "stop", "dns_udp") for r in rows)
    ):
        raise ValueError("DNS window incomplete, capture errors or packet loss")
    queries, found = {}, []
    for number, row in enumerate(rows, 1):
        if (
            row["event"] != "dns_udp"
            or not starts[0]["ts"] <= row["ts"] <= guest["end"]
        ):
            continue
        message = dns_message(bytes.fromhex(row["payload_hex"]))
        flags = message["flags"]
        if not flags & 0x8000:
            if row["destination_port"] != 53:
                raise ValueError("invalid DNS query tuple")
            key = (
                message["id"],
                tuple(message["questions"]),
                row["source_ip"],
                row["source_port"],
                row["destination_ip"],
            )
            queries[key] = row["ts"]
            continue
        key = (
            message["id"],
            tuple(message["questions"]),
            row["destination_ip"],
            row["destination_port"],
            row["source_ip"],
        )
        if row["source_port"] != 53 or key not in queries or row["ts"] < queries[key]:
            raise ValueError("unmatched DNS response")
        if flags & 0x0200:
            raise ValueError("truncated DNS response")
        if flags & 15:
            continue
        host, _, cls = message["questions"][0]
        if cls != 1:
            continue
        reachable = {host: float("inf")}
        for _ in range(len(message["answers"]) + 1):
            added = False
            for answer in message["answers"]:
                if (
                    answer["type"] == 5
                    and answer["host"] in reachable
                    and answer["value"] not in reachable
                ):
                    reachable[answer["value"]] = min(
                        reachable[answer["host"]], answer["ttl"]
                    )
                    added = True
            if not added:
                break
        for answer in message["answers"]:
            if answer["type"] in (1, 28) and answer["host"] in reachable:
                found.append(
                    {
                        "host": host,
                        "ip": answer["value"],
                        "ts": row["ts"],
                        "ttl": min(reachable[answer["host"]], answer["ttl"]),
                        "dns_line": number,
                    }
                )
    return found


def attribution(guest, events, expected, refusals, connections):
    records = bindings(guest)
    agents = descendants(events, guest["roots"])
    calls = []
    for serial, rows in events.items():
        for call in rows:
            if (
                call.get("type") != "SYSCALL"
                or call.get("key") != "rollout_connect"
                or int(call["pid"]) not in agents
            ):
                continue
            if call.get("arch") != "c000003e" or int(call["syscall"]) != 42:
                raise ValueError("unsupported connect audit architecture/syscall")
            addresses = [row for row in rows if row.get("type") == "SOCKADDR"]
            if len(addresses) != 1:
                raise ValueError("missing connect SOCKADDR")
            raw = bytes.fromhex(addresses[0]["saddr"])
            family = int.from_bytes(raw[:2], "little")
            if family == 0 and raw == bytes(16) and call.get("success") == "yes":
                continue
            if family in (1, 16):
                continue
            if family not in (2, 10) or len(raw) < (16 if family == 2 else 28):
                raise ValueError("unsupported connect address")
            port = int.from_bytes(raw[2:4], "big")
            if port != 443:
                continue
            ip = str(ipaddress.ip_address(raw[4:8] if family == 2 else raw[8:24]))
            stamp = float(call["msg"].split("(")[1].split(":")[0])
            matches = [
                r
                for r in records
                if r["ip"] == ip
                and allowed(r["host"], expected)
                and guest["start"] <= r["ts"] <= guest["end"]
                and -TIME_TOLERANCE <= stamp - r["ts"] <= r["ttl"]
                and r["ttl"] > 0
            ]
            calls.append(
                {
                    "audit_serial": serial,
                    "pid": int(call["pid"]),
                    "exe": call.get("exe"),
                    "ts": stamp,
                    "ip": ip,
                    "port": port,
                    "dns_matches": matches,
                }
            )
    covered = []
    if calls and all(c["dns_matches"] for c in calls):
        for refusal in refusals:
            near = [c for c in calls if abs(c["ts"] - refusal["ts"]) <= TIME_TOLERANCE]
            siblings = [
                r
                for r in connections
                if r.get("outcome") == "relayed"
                and isinstance(r.get("sni"), str)
                and allowed(r["sni"], expected)
                and abs(r["ts"] - refusal["ts"]) <= TIME_TOLERANCE
            ]
            if (
                near
                and siblings
                and all(
                    any(
                        m["host"] == r["sni"].lower().rstrip(".")
                        for c in near
                        for m in c["dns_matches"]
                    )
                    for r in siblings
                )
            ):
                covered.append(
                    {
                        "connection_id": refusal["connection_id"],
                        "ts": refusal["ts"],
                        "connect_audit_serials": [c["audit_serial"] for c in near],
                        "dns_lines": sorted(
                            {m["dns_line"] for c in near for m in c["dns_matches"]}
                        ),
                    }
                )
    return {
        "covered_no_sni_refusals": covered,
        "agent_connects_443": calls,
        "dns_bindings": records,
        "timestamp_tolerance_seconds": TIME_TOLERANCE,
    }
