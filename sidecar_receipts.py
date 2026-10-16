"""A receipt for every Modal sandbox run, recorded from a Sidecar the sandbox cannot touch.

    modal run sidecar_receipts.py --n 10                      # 10 real installs x 3 cells (sidecar, invm, none)
    modal run sidecar_receipts.py --n 30 --out out-sidecar30
    modal run sidecar_receipts.py --workload https --n 3      # per-connection relay cost, 200 GETs each
    modal run sidecar_receipts.py --n 10 --cells sidecar --allowlist out-sidecar30/allowlist.json --constructed 1

Cells:
  sidecar  main VM sandbox + Garnet Sidecar relay on :443 (SNI recorded, nothing decrypted)
           + in-VM audit recorder (process attribution). One merged receipt per run.
  invm     in-VM audit recorder only (the previous demo).
  none     same image and workload, nothing recorded.
"""
import json, statistics, time
from pathlib import Path

import modal

app = modal.App("garnet-sidecar-receipts")
HERE = Path(__file__).parent
GUEST_PACKAGES = ["git", "curl", "ca-certificates", "auditd", "procps", "python3", "python3-venv", "python3-pip", "nodejs", "npm", "build-essential"]
guest_image = (modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
               .env({"DEBIAN_FRONTEND": "noninteractive"}).apt_install(*GUEST_PACKAGES))
sidecar_image = (modal.Image.debian_slim(python_version="3.12")
                 .add_local_file(HERE / "sidecar" / "recorder.py", "/recorder.py", copy=True))
driver_image = modal.Image.debian_slim()

SIDECAR_NAME = "garnet"
MAIN_MEMORY_MIB = 2048            # what the workload gets in every cell
SIDECAR_RESERVE_MIB = 1024        # Modal minimum reserve for VM sidecars
SIDECAR_CONSUME_MIB = 512
SIDECAR_COVERAGE = ("TCP/443 leaving the main container, relayed by Modal to the Sidecar; host name read from the TLS "
                    "ClientHello SNI, nothing decrypted. Not covered: DNS, any other port, UDP, TLS without SNI "
                    "(refused, recorded as refused_no_sni), traffic from the Sidecar itself.")


@app.function(image=guest_image)
def guest_ready(): return "ok"


@app.function(image=sidecar_image)
def sidecar_ready(): return "ok"


def guest_bundle() -> str:
    import base64, io, tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for p in sorted((HERE / "guest").iterdir()):
            if p.is_file():
                tf.add(p, arcname=p.name)
    return base64.b64encode(buf.getvalue()).decode()


def _exec(c, cmd, timeout):
    p = c.exec("bash", "-lc", cmd, timeout=timeout)
    out, err = p.stdout.read(), p.stderr.read()
    p.wait()
    return p.returncode, out, err


@app.function(image=driver_image, timeout=1800, max_containers=50)
def run_one(spec: dict) -> dict:
    """One sandbox (+ one Sidecar in the sidecar cell), one receipt."""
    cell = spec["cell"]
    t = {}
    t0 = time.monotonic()
    kw = dict(image=modal.Image.from_id(spec["image_id"]), app=app, runtime="vm", timeout=1500, cpu=2)
    if cell == "sidecar":
        kw.update(memory=MAIN_MEMORY_MIB + SIDECAR_RESERVE_MIB,
                  experimental_options={"proxy_traffic_via_sidecar": SIDECAR_NAME, "vm_sidecar_memory_reserve_mib": SIDECAR_RESERVE_MIB})
        if spec.get("main_cidr_empty"):
            # every port other than 443 refused by Modal; 443 goes through the relay (docs: "A Sandbox outbound_cidr_allowlist is allowed")
            kw["outbound_cidr_allowlist"] = []
    else:
        kw.update(memory=MAIN_MEMORY_MIB)
    sb = modal.Sandbox.create("sleep", "infinity", **kw)
    t["create_s"] = time.monotonic() - t0
    result = {"index": spec["index"], "label": spec["label"], "cell": cell, "constructed": spec.get("constructed", False),
              "sandbox_id": sb.object_id, "timings": t}
    sc = None
    try:
        t1 = time.monotonic()
        _exec(sb, "true", 60)
        t["first_exec_s"] = time.monotonic() - t1
        if cell == "sidecar":
            t2 = time.monotonic()
            skw = dict(name=SIDECAR_NAME, image=modal.Image.from_id(spec["sidecar_image_id"]),
                       experimental_memory_reserve_consume_mib=SIDECAR_CONSUME_MIB)
            if spec.get("allowlist") is not None:
                skw["outbound_domain_allowlist"] = spec["allowlist"]
            sc = sb._experimental_sidecars.create("bash", "-c", "mkdir -p /garnet; exec python -u /recorder.py 2>>/garnet/recorder.err", **skw)
            rc, out, err = _exec(sc, "until (echo > /dev/tcp/127.0.0.1/443) 2>/dev/null; do sleep 0.05; done; echo up", 60)
            t["sidecar_up_s"] = time.monotonic() - t2
            result["sidecar_id"] = sc.object_id
        _exec(sb, f"mkdir -p /opt/garnet /work && echo '{spec['bundle']}' | base64 -d | tar -xzf - -C /opt/garnet", 60)
        if cell in ("sidecar", "invm"):
            t3 = time.monotonic()
            rc, out, err = _exec(sb, f"GARNET_RULES={spec.get('rules', 'nofiles')} bash /opt/garnet/recorder.sh start", 60)
            t["arm_s"] = time.monotonic() - t3
            result["arm"] = {"rc": rc, "out": out.strip(), "err": err.strip()[:300]}
        t4 = time.monotonic()
        rc, out, err = _exec(sb, spec["cmd"], 1200)
        t["workload_s"] = time.monotonic() - t4
        result["workload"] = {"rc": rc, "steps": [l for l in out.splitlines() if l.startswith("::")], "out": out[-600:], "err": err.strip()[-400:]}
        if cell in ("sidecar", "invm"):
            t5 = time.monotonic()
            _exec(sb, "bash /opt/garnet/recorder.sh stop", 60)
            rc, out, err = _exec(sb, "python3 /opt/garnet/receipt.py", 300)
            if rc == 0:
                result["receipt"] = json.loads(out)
            else:
                result["receipt_error"] = err[-1500:]
            t["receipt_s"] = time.monotonic() - t5
        if cell == "sidecar":
            t6 = time.monotonic()
            rc, slog, err = _exec(sc, "cat /garnet/sidecar.log; echo ---ERR; tail -c 1500 /garnet/recorder.err 2>/dev/null", 60)
            log_txt, _, err_txt = slog.partition("---ERR")
            side = [json.loads(l) for l in log_txt.splitlines() if l.strip().startswith("{")]
            result["sidecar_log_lines"] = len(side)
            result["sidecar_stderr"] = err_txt.strip()[-500:]
            t["sidecar_collect_s"] = time.monotonic() - t6
            result["receipt"] = merge(result.get("receipt"), side, result.get("receipt_error"),
                                      allowlist=spec.get("allowlist"), allowlist_source=spec.get("allowlist_source"))
            if spec.get("allowlist") is not None:
                mark_refused_by_policy(result["receipt"])
    finally:
        t["total_s"] = time.monotonic() - t0
        sb.terminate()
    return result


def mark_refused_by_policy(receipt: dict) -> None:
    """Under a Sidecar allowlist, a connection Modal refuses on SNI looks like: upstream TCP opened, ClientHello sent,
    0 bytes returned. Record it as refused_by_policy with the policy source, so a refused host is visible, not silent."""
    sc = receipt.get("sidecar") or {}
    pol = sc.get("policy") or {}
    allowed = set(pol.get("outbound_domain_allowlist") or [])
    for h in sc.get("hosts", []):
        if h.get("relayed") and h.get("bytes_up") and not h.get("bytes_down") and h["host"] not in allowed:
            h["outcomes"] = {"refused_by_policy": h["relayed"], **{k: v for k, v in h["outcomes"].items() if k != "relayed"}}
            h["refused_by_policy"] = h["relayed"]
            h["relayed"] = 0
            h["policy_source"] = f"sidecar.outbound_domain_allowlist ({pol.get('source', 'operator-supplied')})"
    sc["refused_by_policy"] = sum(h.get("refused_by_policy", 0) for h in sc.get("hosts", []))
    sc["relayed"] = sum(h.get("relayed", 0) for h in sc.get("hosts", []))


def merge(invm, side, invm_error=None, allowlist=None, allowlist_source=None) -> dict:
    """Guest receipt + sidecar{...} + agreement{...}. The guest receipt may be missing."""
    cap = (invm or {}).get("capture") if isinstance((invm or {}).get("capture"), dict) else {}
    win = cap.get("window") or {}
    w0, w1 = win.get("start", 0), win.get("stop", float("inf"))
    probes = [r for r in side if "client" in r and str(r.get("client", "")).startswith("127.")]  # the driver's own readiness check on 127.0.0.1:443
    conns = [r for r in side if "client" in r and r not in probes]
    by_host, in_window, outside = {}, {}, {"before_window": 0, "after_window": 0}
    for r in conns:
        h = r.get("sni") or ("(no SNI)" if r.get("outcome") == "refused_no_sni" else "(no ClientHello)")
        e = by_host.setdefault(h, {"host": h, "connections": 0, "relayed": 0, "refused_or_failed": 0, "bytes_up": 0, "bytes_down": 0, "upstreams": set(), "outcomes": {}})
        e["connections"] += 1
        e["outcomes"][r.get("outcome")] = e["outcomes"].get(r.get("outcome"), 0) + 1
        if r.get("outcome") == "relayed":
            e["relayed"] += 1; e["bytes_up"] += r.get("bytes_up", 0); e["bytes_down"] += r.get("bytes_down", 0)
        else:
            e["refused_or_failed"] += 1
        if r.get("upstream"):
            e["upstreams"].add(r["upstream"])
        if r.get("sni") and r.get("outcome") != "refused_no_sni":
            if r["ts"] < w0:
                outside["before_window"] += 1
            elif r["ts"] > w1:
                outside["after_window"] += 1
            else:
                in_window.setdefault(r["sni"], 0)
                in_window[r["sni"]] += 1
    hosts = sorted(({**e, "upstreams": sorted(e["upstreams"])} for e in by_host.values()), key=lambda e: (-e["connections"], e["host"]))
    invm_hosts = {}
    for d in ((invm or {}).get("network", {}).get("outbound_destinations") or []):
        if d.get("port") != 443:
            continue
        for n in str(d.get("destination") or "").split("|"):
            n = n.strip()
            if n:
                invm_hosts.setdefault(n, []).extend(c.get("chain") for c in d.get("chains") or [])
    both = sorted(set(in_window) & set(invm_hosts))
    only_side = sorted(set(in_window) - set(invm_hosts))
    only_vm = sorted(set(invm_hosts) - set(in_window))
    if invm is None:
        verdict = "no_in_vm_record"
    elif only_side:
        verdict = "in_vm_record_incomplete_or_altered"
    else:
        verdict = "agree"
    out = dict(invm or {"schema": "garnet.sandbox-receipt/0.2", "capture": None, "capture_error": (invm_error or "")[-500:]})
    out["schema"] = "garnet.sandbox-receipt/0.2"
    out["sidecar"] = {
        "recorder": "garnet-sidecar-sni-relay", "name": SIDECAR_NAME,
        "connections": len(conns), "relayed": sum(1 for r in conns if r.get("outcome") == "relayed"),
        "readiness_probes_excluded": len(probes),
        "policy": ({"outbound_domain_allowlist": list(allowlist), "source": allowlist_source or "operator-supplied",
                    "enforced_by": "Modal, on the Sidecar's outbound connections, matched on TLS ClientHello SNI"}
                   if allowlist is not None else None),
        "hosts": hosts,
        "connections_outside_in_vm_window": outside,
        "coverage": SIDECAR_COVERAGE,
        "original_destination_visible": any(r.get("orig_dst") for r in conns),
    }
    out["agreement"] = {
        "verdict": verdict,
        "both": both, "sidecar_only": only_side, "in_vm_only": only_vm,
        "in_vm_declared_complete": cap.get("declared_complete"),
        "in_vm_lost": (cap.get("kernel_counters_at_stop") or {}).get("lost"),
        "process_by_host": {h: sorted({str(c) for c in v}) for h, v in invm_hosts.items()},
        "meaning": ("agree: every host the Sidecar relayed inside the in-VM window also appears in the in-VM record. "
                    "in_vm_record_incomplete_or_altered: the Sidecar relayed a host the in-VM record lacks; the record "
                    "inside the sandbox (which root in the sandbox can edit) is incomplete or was changed."),
    }
    return out


def _p(xs, q):
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[max(0, min(len(xs) - 1, round(q * (len(xs) - 1))))], 3)


def _stats(rows, key):
    xs = [r["timings"][key] for r in rows if key in r["timings"]]
    return {"n": len(xs), "p50": round(statistics.median(xs), 2), "p95": _p(xs, 0.95), "max": round(max(xs), 2)} if xs else None


MIXED30_NPM = ["lodash", "react", "express", "axios", "typescript", "vite", "eslint", "jest", "zod", "puppeteer",
               "cypress", "sqlite3", "canvas", "node-sass", "serverless", "sharp", "esbuild", "prisma", "tailwindcss", "pnpm"]
MIXED30_PIP = ["requests", "numpy", "pandas", "flask", "fastapi", "pydantic", "httpx", "boto3", "pillow", "rich"]


def install_specs(n):
    """Real packages (from cohorts.py's lists), the same ones in every cell. n=30 is the full
    mixed list (20 npm incl. the six known postinstall fetchers, 10 PyPI); smaller n takes a stride."""
    full = [("npm", p) for p in MIXED30_NPM] + [("pip", p) for p in MIXED30_PIP]
    if n < len(full):
        step = len(full) / n
        full = [full[int(i * step)] for i in range(n)]
    return [{"label": f"{eco}:{p}", "cmd": f"bash /opt/garnet/workload-install.sh {eco} '{p}'"} for eco, p in full[:n]]


@app.local_entrypoint()
def main(n: int = 10, cells: str = "sidecar,invm,none", workload: str = "install", out: str = "out-sidecar",
         allowlist: str = "", constructed: int = 0, https_count: int = 200, main_cidr_empty: int = 0, constructed_port80: int = 0):
    bundle = guest_bundle()
    image_id, sidecar_image_id = guest_image.object_id, sidecar_image.object_id
    if workload == "install":
        base = install_specs(n)
    elif workload == "https":
        base = [{"label": "https:registry.npmjs.org", "cmd": f"bash /opt/garnet/workload-https.sh {https_count} https://registry.npmjs.org/-/ping"} for _ in range(n)]
    else:
        raise SystemExit("workload: install | https")
    allow, allow_src = None, None
    if allowlist:
        _a = json.loads(Path(allowlist).read_text())
        allow = _a["allowlist"]
        allow_src = f"evidence-derived: union of Sidecar-relayed hosts over {_a.get('derived_from_runs', '?')} real runs ({Path(allowlist).name})"
        print(f"sidecar outbound_domain_allowlist = {allow}", flush=True)
    specs, i = [], 0
    for cell in cells.split(","):
        for b in base:
            specs.append({**b, "index": i, "cell": cell, "image_id": image_id, "sidecar_image_id": sidecar_image_id, "bundle": bundle,
                          "allowlist": allow, "allowlist_source": allow_src, "main_cidr_empty": bool(main_cidr_empty)}); i += 1
        for k in range(constructed_port80 if cell == "sidecar" else 0):
            # constructed: plain HTTP on port 80 (not relayed; governed by the main container's own outbound_cidr_allowlist)
            specs.append({"label": "constructed:curl-http80-example.com", "constructed": True, "index": i, "cell": cell, "image_id": image_id,
                          "sidecar_image_id": sidecar_image_id, "bundle": bundle, "allowlist": allow, "allowlist_source": allow_src, "main_cidr_empty": bool(main_cidr_empty),
                          "cmd": "echo '::step constructed curl http://example.com:80'; curl -sS -m 15 -o /dev/null -w '%{http_code}\\n' http://example.com/; echo \"::done rc=$?\""}); i += 1
        for k in range(constructed if cell == "sidecar" else 0):
            # constructed: a step that reaches a host outside the evidence-derived allowlist (labelled as such)
            specs.append({"label": "constructed:curl-example.com", "constructed": True, "index": i, "cell": cell, "image_id": image_id,
                          "sidecar_image_id": sidecar_image_id, "bundle": bundle, "allowlist": allow, "allowlist_source": allow_src, "main_cidr_empty": bool(main_cidr_empty),
                          "cmd": "echo '::step constructed curl https://example.com'; curl -sS -m 15 -o /dev/null -w '%{http_code}\\n' https://example.com/; echo \"::done rc=$?\""}); i += 1
    started = time.time()
    print(f"launching {len(specs)} VM sandboxes: {n} x cells [{cells}] ({workload}) ...", flush=True)
    results = list(run_one.map(specs, order_outputs=False))
    wall = time.time() - started
    print(summarize(results, workload, wall, Path(out), allow), flush=True)


def summarize(results, workload, wall, outdir: Path, allow=None) -> str:
    (outdir / "receipts").mkdir(parents=True, exist_ok=True)
    for r in results:
        if "receipt" in r:
            safe = r["label"].replace("/", "_").replace(":", "-").replace("@", "")
            (outdir / "receipts" / f"run-{r['index']:03d}-{r['cell']}-{safe}.json").write_text(json.dumps(r["receipt"], indent=1))
    (outdir / "cohort.json").write_text(json.dumps({"workload": workload, "wall_s": wall, "allowlist": allow,
                                                    "runs": [{k: v for k, v in r.items() if k != "receipt"} for r in results]}, indent=1))
    side = [r for r in results if r["cell"] == "sidecar"]
    L = [f"# Sidecar receipts: {workload}", "", f"{len(results)} VM sandboxes in {wall:.0f}s wall; cells: " +
         ", ".join(f"{c}={sum(1 for r in results if r['cell'] == c)}" for c in dict.fromkeys(r["cell"] for r in results)) + "."]
    if side:
        real = [r for r in side if not r.get("constructed")]
        verdicts = {}
        for r in side:
            verdicts[r["receipt"]["agreement"]["verdict"]] = verdicts.get(r["receipt"]["agreement"]["verdict"], 0) + 1
        L += ["", f"## Agreement (sidecar cell, n={len(side)}): " + ", ".join(f"{k}={v}" for k, v in verdicts.items())]
        # cohort comparison on the Sidecar record (the one the sandbox cannot edit), per group
        groups = sorted({r["label"].split(":")[0] for r in real})
        union = set()
        same, new = 0, []
        for g in groups:
            members = [r for r in real if r["label"].split(":")[0] == g]
            host_runs = {}
            for r in members:
                for h in r["receipt"]["sidecar"]["hosts"]:
                    if h["relayed"] > 0:
                        host_runs.setdefault(h["host"], []).append(r)
                        union.add(h["host"])
            common = {h for h, rs in host_runs.items() if len(rs) >= max(1, int(0.9 * len(members)))}
            for r in members:
                mine = {h["host"] for h in r["receipt"]["sidecar"]["hosts"] if h["relayed"] > 0}
                extra = sorted(mine - common)
                if extra:
                    new.append((r, extra))
                else:
                    same += 1
            L += ["", f"### {g}: common hosts (>=90% of {len(members)} runs): " + ", ".join(f"`{h}`" for h in sorted(common))]
        L += ["", f"## {same} runs reached only their group's common hosts; {len(new)} reached something new", ""]
        for r, extra in new:
            pb = r["receipt"]["agreement"]["process_by_host"]
            for h in extra:
                L.append(f"- run {r['index']:03d} [{r['label']}]: `{h}` via `{' | '.join(pb.get(h, ['(no in-VM attribution)']))}`")
        cons = [r for r in side if r.get("constructed")]
        for r in cons:
            hs = r["receipt"]["sidecar"]["hosts"]
            step_rc = next((s.split("rc=")[-1] for s in r["workload"]["steps"] if s.startswith("::done")), "?")
            def _h(h):
                if h.get("refused_by_policy") or (h["relayed"] and not h["bytes_down"]):
                    return f"`{h['host']}` refused_by_policy ({h.get('policy_source', 'sidecar.outbound_domain_allowlist')}): upstream TCP opened, {h['bytes_up']} B sent (ClientHello), 0 B returned"
                return f"`{h['host']}` {h['outcomes']}"
            L.append(f"- run {r['index']:03d} [{r['label']}] (constructed): " + "; ".join(_h(h) for h in hs)
                     + f"; curl rc={step_rc} ({r['workload']['err'].strip().splitlines()[-1] if r['workload']['err'].strip() else 'no stderr'})")
        (outdir / "allowlist.json").write_text(json.dumps({"allowlist": sorted(union), "derived_from_runs": len(real)}, indent=1))
        L += ["", f"Evidence-derived allowlist (union of relayed hosts over {len(real)} real runs): " + ", ".join(f"`{h}`" for h in sorted(union))]
        if allow is not None:
            ok = [r for r in real if r["workload"]["rc"] == 0]
            L += ["", f"## Allowlist rerun: sidecar outbound_domain_allowlist = {allow}", f"{len(ok)} of {len(real)} real runs exited 0 with the allowlist on."]
        orig = sum(1 for r in side if r["receipt"]["sidecar"].get("original_destination_visible"))
        L += ["", f"Original destination (SO_ORIGINAL_DST) visible to the Sidecar in {orig} of {len(side)} runs."]
    if workload == "https":
        L += ["", "## Per-connection cost: sequential HTTPS GETs (new TCP connection each), seconds per request", "",
              "| cell | sandboxes | requests | total p50 | total p95 | connect p50 | connect p95 | non-200 |", "|---|---|---|---|---|---|---|---|"]
        for c in dict.fromkeys(r["cell"] for r in results):
            tot, con, codes = [], [], {}
            for r in results:
                if r["cell"] != c:
                    continue
                for s in r["workload"]["steps"]:
                    if s.startswith("::times_total "):
                        tot += [float(x) for x in s.split(" ", 1)[1].split(",") if x]
                    if s.startswith("::times_connect "):
                        con += [float(x) for x in s.split(" ", 1)[1].split(",") if x]
                    if s.startswith("::codes "):
                        codes[r["index"]] = s.split(" ", 1)[1]
            bad = sum(int(v.split()[i]) for v in codes.values() for i in range(0, len(v.split()), 2) if v.split()[i + 1] != "200")
            L.append(f"| {c} | {sum(1 for r in results if r['cell'] == c)} | {len(tot)} | {_p(tot, 0.5)} | {_p(tot, 0.95)} | {_p(con, 0.5)} | {_p(con, 0.95)} | {bad} |")
    L += ["", "## Workload outcomes", ""]
    for c in dict.fromkeys(r["cell"] for r in results):
        rows = [r for r in results if r["cell"] == c]
        bad = [f"{r['label']}={r['workload']['rc']}" for r in rows if r.get("workload", {}).get("rc") != 0]
        L.append(f"- {c}: {len(rows) - len(bad)} of {len(rows)} exited 0" + (f"; non-zero: {', '.join(bad)}" if bad else ""))
    L += ["", "## Cost (seconds per sandbox, p50 / p95, n per cell)", "", "| phase | " + " | ".join(dict.fromkeys(r["cell"] for r in results)) + " |",
          "|---|" + "---|" * len(set(r["cell"] for r in results))]
    for key, label in (("create_s", "sandbox create"), ("sidecar_up_s", "sidecar up (create + listening)"), ("first_exec_s", "first exec"),
                       ("arm_s", "arm in-VM recorder"), ("workload_s", "workload"), ("receipt_s", "build in-VM receipt"),
                       ("sidecar_collect_s", "collect sidecar log"), ("total_s", "total")):
        cells_txt = []
        for c in dict.fromkeys(r["cell"] for r in results):
            s = _stats([r for r in results if r["cell"] == c and not r.get("constructed")], key)
            cells_txt.append(f"{s['p50']} / {s['p95']} (n={s['n']})" if s else "-")
        L.append(f"| {label} | " + " | ".join(cells_txt) + " |")
    inc = [r for r in results if "receipt" in r and r["receipt"].get("capture") and not r["receipt"]["capture"]["declared_complete"]]
    noreceipt = [r for r in results if r["cell"] != "none" and ("receipt" not in r or r["receipt"].get("capture") is None)]
    L += ["", f"In-VM receipts declared incomplete: {len(inc)}; in-VM receipt missing: {len(noreceipt)}."]
    for r in noreceipt:
        L.append(f"- run {r['index']:03d} [{r['cell']} {r['label']}]: {str(r.get('receipt_error') or (r.get('receipt') or {}).get('capture_error'))[:200]}")
    txt = "\n".join(L) + "\n"
    (outdir / "SUMMARY.md").write_text(txt)
    return txt


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "summarize":
        outdir = Path(sys.argv[2])
        cohort = json.loads((outdir / "cohort.json").read_text())
        for r in cohort["runs"]:
            safe = r["label"].replace("/", "_").replace(":", "-").replace("@", "")
            p = outdir / "receipts" / f"run-{r['index']:03d}-{r['cell']}-{safe}.json"
            if p.exists():
                r["receipt"] = json.loads(p.read_text())
        print(summarize(cohort["runs"], cohort["workload"], cohort["wall_s"], outdir, cohort.get("allowlist")))
