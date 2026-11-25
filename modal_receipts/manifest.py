"""Write a portable inventory of the frozen evidence retained for a Harbor job."""

import argparse
import hashlib
import json
import os
from importlib.metadata import distribution
from pathlib import Path

from modal_receipts.integrity import CHECK_RULES, INTEGRITY_SCOPE
from modal_receipts.rollout import CHECKS, SCOPE, result

ARTIFACTS = (
    "guest-capture.json",
    "sidecar-capture.json",
    "rollout-evidence.json",
    "garnet-receipt.json",
)
LIMITS = [
    "Guest root can alter or erase guest evidence; the sidecar is an independent SNI observer, not a kernel trace.",
    "Flags are observations, not findings of intent, correctness, or cheating.",
    "Not observed within scope is not proof of absence. Unknown is not clean.",
    "Hashes cover host-retained bytes. This manifest is not signed and does not prove source integrity.",
]


def recorder_identity():
    package = distribution("modal-receipts")
    direct_url = json.loads(package.read_text("direct_url.json") or "{}")
    commit = direct_url.get("vcs_info", {}).get("commit_id")
    source = "installed VCS metadata" if commit else None
    if not commit and (commit := os.getenv("GARNET_RECORDER_COMMIT")):
        source = "operator-declared"
    return {"version": package.version, "commit": commit, "commit_source": source}


def load_evidence(path):
    try:
        evidence = json.loads(path.read_text())
        if not isinstance(evidence, dict) or evidence.get("frozen_at") != "AGENT_END":
            raise ValueError("not frozen at AGENT_END")
        return evidence, None
    except (OSError, ValueError) as exc:
        return (
            {},
            f"Frozen rollout evidence unavailable: {exc.strerror if isinstance(exc, OSError) else exc}",
        )


def artifact_hash(path):
    try:
        with path.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError:
        return None


def trial_manifest(job_dir, trial):
    directory = job_dir / trial.trial_name
    if directory.parent != job_dir or directory.name != trial.trial_name:
        raise ValueError(f"Not a trial directory name: {trial.trial_name!r}")
    evidence, error = load_evidence(directory / "rollout-evidence.json")
    checks = {
        name: evidence.get("checks", {}).get(name)
        or result("unknown", error or "check not recorded", [])
        for name in (*CHECKS, *CHECK_RULES)
    }
    states = {check["state"] for check in checks.values()}
    verdict = (
        "observed"
        if "observed" in states
        else "unknown"
        if "unknown" in states
        else "not_observed_within_scope"
    )
    return {
        "trial": trial.trial_name,
        "task": trial.task_name,
        "recorder": evidence.get("recorder"),
        "verdict": verdict,
        "coverage_incomplete": "unknown" in states
        or bool(evidence.get("details", {}).get("network_capture", {}).get("partial")),
        "coverage": evidence.get("scope", {}),
        "checks": checks,
        "artifact_sha256": {
            f"{trial.trial_name}/{name}": artifact_hash(directory / name)
            for name in ARTIFACTS
        },
    }


def write_job_manifest(job_dir, trials):
    manifest = {
        "schema": "garnet.harbor-integrity/v1",
        "recorder": recorder_identity(),
        "scope": {**SCOPE, **INTEGRITY_SCOPE},
        "limits": LIMITS,
        "trials": sorted(
            (trial_manifest(job_dir, trial) for trial in trials),
            key=lambda row: row["trial"],
        ),
    }
    (job_dir / "integrity-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    lines = [
        "# Harbor rollout integrity",
        "",
        "See [integrity-manifest.json](integrity-manifest.json) for coverage and artifact hashes.",
        "",
        "| Trial | Verdict | Coverage incomplete |",
        "| --- | --- | --- |",
    ]
    for row in manifest["trials"]:
        name = row["trial"].replace("|", "\\|").replace("\n", " ")
        incomplete = "yes" if row["coverage_incomplete"] else "no"
        lines.append(f"| {name} | {row['verdict']} | {incomplete} |")
    lines += ["", *(f"- {limit}" for limit in LIMITS)]
    (job_dir / "integrity-manifest.md").write_text("\n".join(lines) + "\n")
    return manifest


def baseline_hosts(job_dir):
    hosts = set()
    captures = partial = 0
    for path in sorted(job_dir.glob("*/rollout-evidence.json")):
        evidence, error = load_evidence(path)
        if error:
            continue
        network = evidence.get("details", {}).get("network_capture", {})
        relayed = network.get("relayed_hosts")
        if not isinstance(relayed, list) or not all(
            isinstance(host, str) for host in relayed
        ):
            continue
        captures += 1
        partial += bool(network.get("partial"))
        hosts.update(relayed)
    if not captures:
        raise ValueError("No frozen network captures found in the baseline job")
    return sorted(hosts), captures, partial


def main():
    parser = argparse.ArgumentParser(
        description="Derive candidate expected SNI from a trusted baseline job."
    )
    parser.add_argument("job_dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        hosts, captures, partial = baseline_hosts(args.job_dir)
    except ValueError as exc:
        parser.error(str(exc))
    args.output.write_text(json.dumps(hosts, indent=2) + "\n")
    print(
        f"Wrote {len(hosts)} hosts from {captures} frozen captures ({partial} with partial network coverage)"
    )


if __name__ == "__main__":
    main()
