"""Replay retained DNS payloads; discarded error-packet bytes cannot be recovered."""

import json
import socket
import struct
from pathlib import Path

from modal_receipts.dns_capture import packet_record


def replay(root):
    results = []
    for task in ("fix-git", "log-summary-date-ranges"):
        capture = json.loads(
            (root / "oracle" / f"{task}-1" / "guest-capture.json").read_text()
        )
        rows = [json.loads(line) for line in capture["dns_capture"]["log"].splitlines()]
        replayed = 0
        for row in rows:
            if row["event"] != "dns_udp":
                continue
            payload = bytes.fromhex(row["payload_hex"])
            udp = (
                struct.pack(
                    "!HHHH",
                    row["source_port"],
                    row["destination_port"],
                    len(payload) + 8,
                    0,
                )
                + payload
            )
            ip = struct.pack(
                "!BBHHHBBH4s4s",
                0x45,
                0,
                20 + len(udp),
                0,
                0,
                64,
                17,
                0,
                socket.inet_aton(row["source_ip"]),
                socket.inet_aton(row["destination_ip"]),
            )
            parsed = packet_record(bytes(12) + b"\x08\x00" + ip + udp, row["ts"])
            assert parsed["payload_hex"] == row["payload_hex"]
            replayed += 1
        results.append(
            {
                "task": task,
                "retained_dns_payloads_replayed": replayed,
                "original_errors": [r for r in rows if r["event"] == "error"],
                "error_packet_replay": "unavailable: old capture did not retain error packet bytes; original L4 protocol cannot be identified",
            }
        )
    return results


if __name__ == "__main__":
    print(json.dumps(replay(Path("samples/harbor-proof-frozen-live")), indent=2))
