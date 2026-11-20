"""Prepare auditable local variants of three cached Terminal-Bench 2.0 tasks."""

import hashlib
import json
import re
import shutil
import sys
import urllib.request
from pathlib import Path

TASKS = ("fix-git", "log-summary-date-ranges", "regex-log")
SOURCE_COMMIT = "2fd12b88aafdd04a52c298e3940bcb189f9766d6"
ROOT = Path(__file__).resolve().parents[1] / "samples" / "harbor-proof"


def derive_policy(source):
    provenance = {}
    for name in TASKS:
        path = next(Path(source).glob(f"{name}__*/rollout-evidence.json"))
        evidence = json.loads(path.read_text())
        sidecar = json.loads((path.parent / "sidecar-capture.json").read_text())
        hosts = sorted(
            {
                row["sni"]
                for line in sidecar["log"].splitlines()
                if (row := json.loads(line)).get("outcome") == "relayed"
                and row.get("sni")
                and evidence["window"]["start"]
                <= row["ts"]
                <= evidence["window"]["end"]
                and not row.get("client", "").startswith(("127.", "[::1]"))
            }
        )
        expected = sorted(set(hosts) | {"ai-gateway.vercel.sh"})
        (ROOT / "tasks" / name / "expected-hosts.json").write_text(
            json.dumps(expected) + "\n"
        )
        provenance[name] = {
            "oracle_trial": path.parent.name,
            "oracle_hosts": hosts,
            "model_endpoint": "ai-gateway.vercel.sh",
            "expected_hosts": expected,
        }
    (ROOT / "policy-provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n"
    )


def main():
    for name in TASKS:
        source = next((Path.home() / ".cache/harbor/tasks").glob(f"*/{name}"))
        target = ROOT / "tasks" / name
        target.mkdir(parents=True, exist_ok=True)
        for filename in ("instruction.md", "task.toml"):
            shutil.copy2(source / filename, target / filename)
        for directory in ("solution", "tests"):
            shutil.copytree(source / directory, target / directory, dirs_exist_ok=True)
        instruction = target / "instruction.md"
        instruction.write_text(
            "\n".join(line.rstrip() for line in instruction.read_text().splitlines())
            + "\n"
        )
        solution = target / "solution/solve.sh"
        solution.write_text(solution.read_text().rstrip() + "\n")
        config = (target / "task.toml").read_text()
        image = re.search(r'docker_image = "([^"]+)"', config)[1]
        (target / "task.toml").write_text(
            re.sub(r"^docker_image = .*\n", "", config, flags=re.MULTILINE)
            + '\nnetwork_mode = "public"\n'
        )
        (target / "environment").mkdir(exist_ok=True)
        (target / "environment/Dockerfile").write_text(
            f"FROM {image}\n"
            "RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y "
            "auditd python3 curl procps ca-certificates && rm -rf /var/lib/apt/lists/*\n"
        )
        url = (
            "https://raw.githubusercontent.com/harbor-framework/terminal-bench-2/"
            f"{SOURCE_COMMIT}/{name}/solution/solve.sh"
        )
        with urllib.request.urlopen(url, timeout=30) as response:
            answer = response.read()
        if answer != (source / "solution/solve.sh").read_bytes():
            raise ValueError(f"Public answer differs from cached task: {name}")
        (target / "proof-source.json").write_text(
            json.dumps(
                {"url": url, "sha256": hashlib.sha256(answer).hexdigest()}, indent=2
            )
            + "\n"
        )
        (target / "expected-hosts.json").write_text("[]\n")
        print(f"{name}: cached oracle matches pinned public answer")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--derive-policy":
        derive_policy(sys.argv[2])
    else:
        main()
