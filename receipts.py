"""Every sandbox run gets a receipt.

    modal run receipts.py                              # 100 real dependency installs, one per VM sandbox
    modal run receipts.py --limit 10                   # the one-minute version
    modal run receipts.py --workload swebench --limit 10
    modal run receipts.py --workload bench --bench-each 10   # recorder cost, with vs without

Each run is one Modal VM Sandbox (runtime="vm") executing a scripted coding-agent
task on a real open-source repository. The recorder in the image is the Linux
kernel's audit subsystem plus an in-guest DNS forwarder. Each receipt declares its
own coverage from the kernel's counters. Nothing is inferred, nothing is sent
anywhere: receipts come back to your terminal and ./out/.
"""
import json, os, statistics, time
from pathlib import Path

import modal

app = modal.App("garnet-sandbox-receipts")

GUEST_PACKAGES = ["git", "curl", "ca-certificates", "auditd", "procps", "python3", "python3-venv", "python3-pip", "nodejs", "npm", "build-essential"]
guest_image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .env({"DEBIAN_FRONTEND": "noninteractive"})
    .apt_install(*GUEST_PACKAGES)
)
driver_image = modal.Image.debian_slim()
GUEST_DIR = Path(__file__).parent / "guest"


@app.function(image=guest_image)
def guest_image_ready() -> str:
    """Exists so `modal run` builds the guest image up front; returns nothing useful."""
    return "ok"


def guest_bundle() -> str:
    """The recorder + workload scripts, base64 tar, written into each sandbox at start."""
    import base64, io, tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for p in sorted(GUEST_DIR.iterdir()):
            if p.is_file():
                tf.add(p, arcname=p.name)
    return base64.b64encode(buf.getvalue()).decode()


def sandbox_image(spec: dict):
    if "image_id" in spec:
        return modal.Image.from_id(spec["image_id"])
    return modal.Image.from_registry(spec["registry_image"]).env({"DEBIAN_FRONTEND": "noninteractive"}).apt_install("auditd", "procps", "python3")

DEFAULT_REPO = "https://github.com/pallets/click"


def _exec(sb, cmd, timeout):
    p = sb.exec("bash", "-lc", cmd, timeout=timeout)
    out = p.stdout.read()
    err = p.stderr.read()
    p.wait()
    return p.returncode, out, err


@app.function(image=driver_image, timeout=1800, max_containers=50)
def run_one(spec: dict) -> dict:
    """One sandbox, one receipt. spec = {index, record, constructed, repo}"""
    t = {}
    t0 = time.monotonic()
    sb = modal.Sandbox.create(
        "sleep", "infinity", image=sandbox_image(spec), app=app, runtime="vm",
        timeout=1500, cpu=2, memory=2048,
    )
    t["create_s"] = time.monotonic() - t0
    t1 = time.monotonic()
    _exec(sb, "true", 60)
    t["first_exec_s"] = time.monotonic() - t1
    result = {"index": spec["index"], "label": spec["label"], "record": spec["record"],
              "constructed": spec.get("constructed", False), "sandbox_id": sb.object_id, "timings": t}
    try:
        _exec(sb, f"mkdir -p /opt/garnet /work && echo '{spec['bundle']}' | base64 -d | tar -xzf - -C /opt/garnet", 60)
        for path, b64 in spec.get("files", {}).items():
            _exec(sb, f"echo '{b64}' | base64 -d > {path}", 60)
        if spec["record"]:
            t2 = time.monotonic()
            rc, out, err = _exec(sb, f"GARNET_RULES={spec.get('rules', 'full')} bash /opt/garnet/recorder.sh start", 60)
            t["arm_s"] = time.monotonic() - t2
            result["arm"] = {"rc": rc, "out": out.strip(), "err": err.strip()[:500]}
        t3 = time.monotonic()
        rc, out, err = _exec(sb, spec["cmd"], 1200)
        t["workload_s"] = time.monotonic() - t3
        result["workload"] = {"rc": rc, "steps": [l for l in out.splitlines() if l.startswith("::")],
                              "out": out[-800:], "err": err.strip()[-500:]}
        if spec["record"]:
            rc2, out2, _ = _exec(sb, "cat /proc/meminfo | head -3; ps -o rss=,comm= -C auditd,python3 2>/dev/null | sort -rn | head -4; wc -c < /var/log/audit/audit.log", 30)
            result["resources"] = out2.strip()[-600:]
        if spec["record"]:
            t4 = time.monotonic()
            _exec(sb, "bash /opt/garnet/recorder.sh stop", 60)
            rc, out, err = _exec(sb, "python3 /opt/garnet/receipt.py", 300)
            t["receipt_s"] = time.monotonic() - t4
            if rc == 0:
                result["receipt"] = json.loads(out)
            else:
                result["receipt_error"] = err[-2000:]
    finally:
        t["total_s"] = time.monotonic() - t0
        sb.terminate()
    return result


def _p(xs, q):
    if len(xs) == 0:
        return None
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, round(q * (len(xs) - 1))))
    return round(xs[k], 2)


def _stats(rows, key):
    xs = [r["timings"][key] for r in rows if key in r["timings"]]
    if len(xs) == 0:
        return None
    return {"n": len(xs), "median": round(statistics.median(xs), 2), "p95": _p(xs, 0.95), "max": round(max(xs), 2)}


@app.local_entrypoint()
def main(workload: str = "install", runs: int = 100, baseline: int = 0, constructed: int = 0,
         repo: str = DEFAULT_REPO, out: str = "out", bench_each: int = 10, limit: int = 0, only: str = ""):
    """workload: install (default: one real top npm/PyPI package per sandbox, nothing constructed),
    swebench (SWE-bench Lite rollouts in the official instance images), task (scripted coding
    task on `repo`), bench / bench-rules (recorder cost, recorded vs unrecorded)."""
    import cohorts
    image_id = guest_image.object_id
    print(f"guest image {image_id} built", flush=True)
    bundle = guest_bundle()
    if workload == "task":
        base = cohorts.task_specs(runs, repo, constructed)
    elif workload == "install":
        base = cohorts.install_specs()
    elif workload == "bench":
        base = cohorts.bench_specs(bench_each)
    elif workload == "bench-rules":
        base = cohorts.bench_specs(bench_each, profiles=("repo", "files"), rulesets=("full", "nofiles"))
    elif workload == "swebench":
        base = cohorts.swebench_specs(str(Path(__file__).parent / "swebench_lite_rows.json"), limit if limit > 0 else 100, only)
    else:
        raise SystemExit(f"unknown workload {workload}")
    if limit > 0:
        base = base[:limit]
    specs = []
    def with_image(b):
        return {} if "registry_image" in b else {"image_id": image_id}
    for i, b in enumerate(base):
        specs.append({**b, **with_image(b), "index": i, "record": True, "bundle": bundle})
    n = len(base)
    for i, b in enumerate(base[:baseline] if baseline > 0 else []):
        specs.append({**b, **with_image(b), "index": n + i, "record": False, "constructed": False, "bundle": bundle})
    runs, baseline = n, len(specs) - n
    started = time.time()
    print(f"launching {runs} recorded + {baseline} unrecorded VM sandboxes ({workload}) ...", flush=True)
    results = list(run_one.map(specs, order_outputs=False))
    wall = time.time() - started

    summary = summarize(results, workload, repo, wall, Path(out))
    print(summary)
    print(f"receipts in {out}/receipts, summary in {out}/SUMMARY.md")


def _group(label: str) -> str:
    """Cohort comparison is within a group: npm vs pip installs, one task, one bench profile."""
    return label.split(":")[0] if ":" in label else label


def summarize(results, workload, repo, wall, outdir) -> str:
    """Write out/receipts, out/SUMMARY.md, out/cohort.json; return the summary text."""
    (outdir / "receipts").mkdir(parents=True, exist_ok=True)
    recorded = [r for r in results if r["record"]]
    plain = [r for r in results if not r["record"]]
    for r in recorded:
        if "receipt" in r:
            safe = r["label"].replace("/", "_").replace(":", "-").replace("@", "")
            (outdir / "receipts" / f"run-{r['index']:03d}-{safe}{'-constructed' if r['constructed'] else ''}.json").write_text(json.dumps(r["receipt"], indent=1))

    complete = [r for r in recorded if "receipt" in r and r["receipt"]["capture"]["declared_complete"]]
    incomplete = [r for r in recorded if "receipt" in r and not r["receipt"]["capture"]["declared_complete"]]
    failed = [r for r in recorded if "receipt" not in r]

    groups = sorted({_group(r["label"]) for r in complete})
    common = set()
    runs_with_novel = {}
    for g in groups:
        members = [r for r in complete if _group(r["label"]) == g]
        dest_runs = {}
        for r in members:
            for d in r["receipt"]["network"]["outbound_destinations"]:
                dest_runs.setdefault(f"{d['destination']}:{d['port']}", []).append(r)
        n = len(members)
        g_common = {k for k, rs in dest_runs.items() if len(rs) >= max(1, int(0.9 * n))}
        common |= {f"{g}: {k}" for k in g_common}
        for k, rs in dest_runs.items():
            if k in g_common:
                continue
            for r in rs:
                runs_with_novel.setdefault(r["index"], []).append(k)
    only_common = [r for r in complete if r["index"] not in runs_with_novel]

    lines = []
    lines.append(f"# Sandbox receipts: {workload}" + (f" on {repo}" if workload == "task" else ""))
    lines.append("")
    lines.append(f"{len(recorded)} recorded runs, {len(plain)} unrecorded runs, {wall:.0f}s wall for the whole cohort.")
    lines.append(f"Receipts: {len(complete)} declared complete, {len(incomplete)} declared incomplete, {len(failed)} no receipt.")
    lines.append("")
    lines.append(f"## {len(only_common)} runs contacted only their group's common hosts ({len(common)} across {len(groups)} group{'s' if len(groups) != 1 else ''}). {len(runs_with_novel)} contacted something new.")
    lines.append("")
    for k in sorted(common):
        lines.append(f"- `{k}`")
    lines.append("")
    for idx, keys in sorted(runs_with_novel.items()):
        r = next(x for x in complete if x["index"] == idx)
        tag = " (constructed)" if r["constructed"] else ""
        tag += f" [{r['label']}]"
        for k in keys:
            d = next(d for d in r["receipt"]["network"]["outbound_destinations"] if f"{d['destination']}:{d['port']}" == k)
            chain = d["chains"][0]["chain"] if len(d["chains"]) > 0 else "?"
            lines.append(f"- run {idx:03d}{tag}: `{k}` via `{chain}`")
    lines.append("")
    lines.append("## Workload outcomes")
    lines.append("")
    rcs = {}
    for r in results:
        rcs.setdefault((r["label"], r["record"]), []).append(r["workload"]["rc"] if "workload" in r else None)
    bad = [(k, v) for k, v in rcs.items() if any(x != 0 for x in v)]
    lines.append(f"{len(results) - len(bad)} of {len(results)} (label, recorded) groups exited 0." + (" Non-zero: " + ", ".join(f"{k[0]}{'' if k[1] else ' (unrecorded)'}={v}" for k, v in bad[:30]) if bad else ""))
    if workload.startswith("bench"):
        lines.append("")
        lines.append("## Bench: workload seconds, recorded vs unrecorded")
        lines.append("")
        lines.append("| profile | recorded median / p95 | unrecorded median / p95 | audit log bytes (median) |")
        lines.append("|---|---|---|---|")
        for prof in sorted({r["label"] for r in results}):
            a = _stats([r for r in recorded if r["label"] == prof], "workload_s")
            b = _stats([r for r in plain if r["label"] == prof], "workload_s")
            logs = sorted(int(r["resources"].strip().splitlines()[-1]) for r in recorded if r["label"] == prof and "resources" in r and r["resources"].strip().splitlines()[-1].isdigit())
            lines.append(f"| {prof} | {a['median']} / {a['p95']} | {b['median'] if b else '-'} / {b['p95'] if b else '-'} | {logs[len(logs)//2] if logs else '-'} |")
    lines.append("")
    lines.append("## Cost (seconds, per sandbox)")
    lines.append("")
    lines.append("| phase | recorded | unrecorded |")
    lines.append("|---|---|---|")
    for key, label in (("create_s", "sandbox create"), ("first_exec_s", "first exec"), ("arm_s", "arm recorder"), ("workload_s", "workload"), ("receipt_s", "build receipt"), ("total_s", "total")):
        a = _stats(recorded, key)
        b = _stats(plain, key)
        fa = f"median {a['median']} / p95 {a['p95']}" if a else "-"
        fb = f"median {b['median']} / p95 {b['p95']}" if b else "-"
        lines.append(f"| {label} | {fa} | {fb} |")
    lines.append("")
    if len(complete) > 0:
        r0 = complete[0]["receipt"]
        lines.append("## Coverage, as declared by the kernel (first complete receipt)")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps({k: r0["capture"][k] for k in ("recorder", "kernel", "kernel_counters_at_stop", "declared_complete", "scope")}, indent=1))
        lines.append("```")
        lines.append("")
        lines.append("## Files touched (first complete receipt)")
        lines.append("")
        for row in r0["files"]["by_top_level"][:8]:
            lines.append(f"- `{row['prefix']}`: {row['paths']} paths")
    for r in incomplete:
        lines.append(f"- run {r['index']:03d} incomplete: {r['receipt']['capture']['incomplete_reasons']}")
    for r in failed:
        lines.append(f"- run {r['index']:03d} no receipt: {str(r.get('receipt_error') or r.get('workload'))[:200]}")
    summary = "\n".join(lines) + "\n"
    (outdir / "SUMMARY.md").write_text(summary)
    (outdir / "cohort.json").write_text(json.dumps({"workload": workload, "repo": repo, "wall_s": wall, "runs": [{k: v for k, v in r.items() if k != "receipt"} for r in results]}, indent=1))


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "summarize":
        outdir = Path(sys.argv[2])
        cohort = json.loads((outdir / "cohort.json").read_text())
        rows = cohort["runs"]
        for r in rows:
            if r["record"]:
                safe = r["label"].replace("/", "_").replace(":", "-").replace("@", "")
                p = outdir / "receipts" / f"run-{r['index']:03d}-{safe}{'-constructed' if r['constructed'] else ''}.json"
                if p.exists():
                    r["receipt"] = json.loads(p.read_text())
        print(summarize(rows, cohort["workload"], cohort["repo"], cohort["wall_s"], outdir))
