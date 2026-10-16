"""Every sandbox run gets a receipt.

    modal run receipts.py                 # 100 recorded runs + 100 unrecorded (cost baseline)
    modal run receipts.py --runs 10 --baseline 10

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

guest_image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .env({"DEBIAN_FRONTEND": "noninteractive"})
    .apt_install("git", "curl", "ca-certificates", "auditd", "procps", "python3", "python3-venv", "python3-pip")
    .add_local_dir(Path(__file__).parent / "guest", remote_path="/opt/garnet", copy=True)
)
driver_image = modal.Image.debian_slim()


@app.function(image=guest_image)
def guest_image_ready() -> str:
    """Exists so `modal run` builds the guest image up front; returns nothing useful."""
    return "ok"

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
        "sleep", "infinity", image=modal.Image.from_id(spec["image_id"]), app=app, runtime="vm",
        timeout=1500, cpu=2, memory=2048,
    )
    t["create_s"] = time.monotonic() - t0
    t1 = time.monotonic()
    _exec(sb, "true", 60)
    t["first_exec_s"] = time.monotonic() - t1
    result = {"index": spec["index"], "record": spec["record"], "constructed": spec["constructed"],
              "sandbox_id": sb.object_id, "timings": t}
    try:
        if spec["record"]:
            t2 = time.monotonic()
            rc, out, err = _exec(sb, "bash /opt/garnet/recorder.sh start", 60)
            t["arm_s"] = time.monotonic() - t2
            result["arm"] = {"rc": rc, "out": out.strip(), "err": err.strip()[:500]}
        t3 = time.monotonic()
        rc, out, err = _exec(sb, f"bash /opt/garnet/workload.sh {spec['repo']} {'constructed' if spec['constructed'] else ''}", 1200)
        t["workload_s"] = time.monotonic() - t3
        result["workload"] = {"rc": rc, "steps": [l for l in out.splitlines() if l.startswith("::")], "err": err.strip()[-500:]}
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
def main(runs: int = 100, baseline: int = 100, constructed: int = 3, repo: str = DEFAULT_REPO, out: str = "out"):
    image_id = guest_image.object_id
    print(f"guest image {image_id} built", flush=True)
    specs = []
    for i in range(runs):
        specs.append({"index": i, "record": True, "constructed": i < constructed, "repo": repo, "image_id": image_id})
    for i in range(baseline):
        specs.append({"index": runs + i, "record": False, "constructed": False, "repo": repo, "image_id": image_id})
    started = time.time()
    print(f"launching {runs} recorded + {baseline} unrecorded VM sandboxes on {repo} ...", flush=True)
    results = list(run_one.map(specs, order_outputs=False))
    wall = time.time() - started

    outdir = Path(out)
    (outdir / "receipts").mkdir(parents=True, exist_ok=True)
    recorded = [r for r in results if r["record"]]
    plain = [r for r in results if not r["record"]]
    for r in recorded:
        if "receipt" in r:
            (outdir / "receipts" / f"run-{r['index']:03d}{'-constructed' if r['constructed'] else ''}.json").write_text(json.dumps(r["receipt"], indent=1))

    complete = [r for r in recorded if "receipt" in r and r["receipt"]["capture"]["declared_complete"]]
    incomplete = [r for r in recorded if "receipt" in r and not r["receipt"]["capture"]["declared_complete"]]
    failed = [r for r in recorded if "receipt" not in r]

    dest_runs = {}
    for r in complete:
        for d in r["receipt"]["network"]["outbound_destinations"]:
            key = f"{d['destination']}:{d['port']}"
            dest_runs.setdefault(key, []).append(r)
    n = len(complete)
    common = {k for k, rs in dest_runs.items() if len(rs) >= max(1, int(0.9 * n))}
    novel = {k: rs for k, rs in dest_runs.items() if k not in common}
    runs_with_novel = {r["index"]: [] for rs in novel.values() for r in rs}
    for k, rs in novel.items():
        for r in rs:
            runs_with_novel[r["index"]].append(k)
    only_common = [r for r in complete if r["index"] not in runs_with_novel]

    lines = []
    lines.append(f"# Sandbox receipts: {repo}")
    lines.append("")
    lines.append(f"{len(recorded)} recorded runs, {len(plain)} unrecorded runs, {wall:.0f}s wall for the whole cohort.")
    lines.append(f"Receipts: {len(complete)} declared complete, {len(incomplete)} declared incomplete, {len(failed)} no receipt.")
    lines.append("")
    lines.append(f"## {len(only_common)} runs contacted the same {len(common)} hosts. {len(runs_with_novel)} contacted something new.")
    lines.append("")
    for k in sorted(common):
        lines.append(f"- `{k}`")
    lines.append("")
    for idx, keys in sorted(runs_with_novel.items()):
        r = next(x for x in complete if x["index"] == idx)
        tag = " (constructed)" if r["constructed"] else ""
        for k in keys:
            d = next(d for d in r["receipt"]["network"]["outbound_destinations"] if f"{d['destination']}:{d['port']}" == k)
            chain = d["chains"][0]["chain"] if len(d["chains"]) > 0 else "?"
            lines.append(f"- run {idx:03d}{tag}: `{k}` via `{chain}`")
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
    (outdir / "cohort.json").write_text(json.dumps({"repo": repo, "wall_s": wall, "runs": [{k: v for k, v in r.items() if k != "receipt"} for r in results]}, indent=1))
    print(summary)
    print(f"receipts in {outdir}/receipts, summary in {outdir}/SUMMARY.md")
