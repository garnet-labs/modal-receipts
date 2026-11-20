"""Pure receipt construction; observations are not policy enforcement."""

import json
from fnmatch import fnmatchcase

SIDECAR_COVERAGE = (
    "TCP/443 leaving the main container, relayed by Modal to the Sidecar; host name read from the TLS "
    "ClientHello SNI, nothing decrypted. Not covered: DNS, any other port, UDP, TLS without SNI "
    "(refused, recorded as refused_no_sni), traffic from the Sidecar itself."
)


def build_receipt(log: str, mode: str, allowed_hosts: list[str]) -> dict:
    records = []
    malformed = []
    for number, line in enumerate(log.splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise TypeError("record is not an object")
            for key in ("bytes_up", "bytes_down"):
                value = record.get(key, 0)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f"invalid {key}")
            if record.get("sni") is not None and not isinstance(record["sni"], str):
                raise ValueError("invalid sni")
            records.append(record)
        except (ValueError, TypeError) as exc:
            malformed.append({"line": number, "error": str(exc)})
    connections = [r for r in records if "outcome" in r]
    hosts = sorted({r["sni"].lower().rstrip(".") for r in connections if r.get("sni")})
    patterns = [p.lower().rstrip(".") for p in allowed_hosts]
    outside = (
        hosts
        if mode == "no-network"
        else (
            [h for h in hosts if not any(fnmatchcase(h, p) for p in patterns)]
            if mode == "allowlist"
            else []
        )
    )
    receipt = {
        "kind": "network-evidence",
        "coverage": SIDECAR_COVERAGE,
        "records": records,
        "hosts": hosts,
        "connection_count": len(connections),
        "bytes_up": sum(r.get("bytes_up", 0) for r in connections),
        "bytes_down": sum(r.get("bytes_down", 0) for r in connections),
        "declared_network_policy": {"mode": mode, "allowed_hosts": allowed_hosts},
        "observed_outside_policy": outside,
        "policy_comparison": "SNI hostname comparison only; IP/CIDR rules cannot be evaluated from SNI",
        "malformed_lines": malformed,
    }
    if malformed:
        receipt["error"] = "Some sidecar log lines could not be parsed"
    return receipt
