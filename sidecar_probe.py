"""One-run probe: VM sandbox + Garnet sidecar recorder. Verifies (a) fail-closed, (b) SNI
recorded without decryption, (c) in-VM audit attribution + agree/disagree, (d) tamper check."""
import base64, io, json, tarfile, time
from pathlib import Path
import modal

app = modal.App("garnet-sidecar-probe")
HERE = Path(__file__).parent
GUEST_PACKAGES = ["git", "curl", "ca-certificates", "auditd", "procps", "python3", "python3-venv", "python3-pip", "nodejs", "npm", "build-essential"]
guest_image = modal.Image.from_registry("ubuntu:24.04", add_python="3.12").env({"DEBIAN_FRONTEND": "noninteractive"}).apt_install(*GUEST_PACKAGES)
sidecar_image = (modal.Image.debian_slim(python_version="3.12")
                 .add_local_file(HERE / "sidecar" / "recorder.py", "/recorder.py", copy=True))


@app.function(image=guest_image)
def guest_ready(): return "ok"


@app.function(image=sidecar_image)
def sidecar_ready(): return "ok"


def bundle() -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for p in sorted((HERE / "guest").iterdir()):
            t.add(p, arcname=p.name)
    return base64.b64encode(buf.getvalue()).decode()


def ex(c, cmd, timeout=120):
    p = c.exec("bash", "-lc", cmd, timeout=timeout)
    out, err = p.stdout.read(), p.stderr.read()
    return p.wait(), out, err


@app.local_entrypoint()
def main(workload: str = "npm install --no-audit --no-fund --loglevel=error puppeteer", tamper: bool = True, diag_only: bool = False):
    T = {}
    t0 = time.monotonic()
    sb = modal.Sandbox.create("sleep", "infinity", app=app, image=guest_image, runtime="vm", timeout=900,
                              cpu=2, memory=4096,
                              experimental_options={"proxy_traffic_via_sidecar": "garnet", "vm_sidecar_memory_reserve_mib": 1024})
    T["create_s"] = round(time.monotonic() - t0, 2)
    print("sandbox", sb.object_id, T)
    try:
        rc, out, err = ex(sb, "curl -sS -m 8 -o /dev/null -w '%{http_code}' https://github.com/ ; echo \" rc=$?\"", 30)
        print("[a] fail-closed before sidecar:", out.strip(), err.strip()[-200:])
        t1 = time.monotonic()
        sc = sb._experimental_sidecars.create("bash", "-c", "mkdir -p /garnet; exec python -u /recorder.py 2>>/garnet/recorder.err", name="garnet", image=sidecar_image,
                                              experimental_memory_reserve_consume_mib=512)
        rc, out, err = ex(sc, "until (echo > /dev/tcp/127.0.0.1/443) 2>/dev/null; do sleep 0.1; done; echo up", 60)
        T["sidecar_up_s"] = round(time.monotonic() - t1, 2)
        print("sidecar", sc.object_id, out.strip(), T)
        rc, out, err = ex(sb, "curl -sS -m 10 -o /dev/null -w '%{http_code}' https://github.com/ ; echo \" rc=$?\"", 30)
        print("[a] after sidecar:", out.strip(), err.strip()[-200:])
        rc, slog0, err = ex(sc, "cat /garnet/sidecar.log; echo ---stderr; cat /garnet/recorder.err 2>/dev/null | tail -20; echo ---diag; python3 -c 'import socket;print(socket.getaddrinfo(\"github.com\",443)[0][4])'; cat /etc/hosts", 30)
        print("[diag] sidecar after first curl:\n", slog0[-2500:], err[-500:])
        if " rc=0" not in out:
            rc, o2, e2 = ex(sb, "cat /etc/hosts; ip route; getent hosts github.com; curl -v -m 10 https://github.com/ 2>&1 | tail -15", 30)
            print("[diag] main container:\n", o2[-2500:])
            if not diag_only:
                pass
            else:
                return
        ex(sb, f"mkdir -p /opt/garnet /work && echo '{bundle()}' | base64 -d | tar -xzf - -C /opt/garnet", 60)
        t2 = time.monotonic()
        rc, out, err = ex(sb, "GARNET_RULES=nofiles bash /opt/garnet/recorder.sh start", 60)
        T["arm_s"] = round(time.monotonic() - t2, 2)
        print("arm", rc, out.strip()[-200:], err.strip()[-200:])
        t3 = time.monotonic()
        rc, out, err = ex(sb, f"cd /work && npm init -y >/dev/null 2>&1; {workload}; echo rc=$?", 600)
        T["workload_s"] = round(time.monotonic() - t3, 2)
        print("workload", out.strip()[-300:], err.strip()[-300:])
        ex(sb, "bash /opt/garnet/recorder.sh stop", 60)
        rc, out, err = ex(sb, "python3 /opt/garnet/receipt.py", 300)
        invm = json.loads(out) if rc == 0 else {"error": err[-1500:]}
        rc, slog, err = ex(sc, "cat /garnet/sidecar.log", 30)
        side = [json.loads(l) for l in slog.splitlines() if l.strip()]
        print("sidecar log:", slog[-1500:])
        print("in-vm receipt capture:", json.dumps(invm.get("capture", invm.get("error")))[:600])
        rep = compare(invm, side)
        print(json.dumps(rep, indent=1)[:3000])
        out = ""
        if tamper:
            # root inside the VM edits the record it can reach: drop every connect to the hosts the sidecar saw
            hosts = sorted({r["sni"] for r in side if r.get("sni")})
            rc, out, err = ex(sb, "grep -c . /var/log/audit/audit.log; sed -i '/type=SOCKADDR/d;/syscall=42 /d' /var/log/audit/audit.log; sed -i '/garnet-connect/d' /garnet/state/dns.log 2>/dev/null; grep -c . /var/log/audit/audit.log", 30)
            print("[d] tamper: audit lines before/after:", out.split())
            rc, out, err = ex(sb, "python3 /opt/garnet/receipt.py", 300)
            invm2 = json.loads(out) if rc == 0 else {"error": err[-1500:]}
            rep2 = compare(invm2, side)
            print("[d] after tamper:", json.dumps(rep2["agreement"], indent=1))
        else:
            rep2 = None
        Path("out").mkdir(exist_ok=True)
        Path("out/sidecar-probe.json").write_text(json.dumps({"timings": T, "sidecar": side, "in_vm": invm, "report": rep, "tamper_report": rep2, "tamper": {"audit_lines_before_after": out.split()} if tamper else None}, indent=1))
    finally:
        T["total_s"] = round(time.monotonic() - t0, 2)
        sb.terminate()
        print("timings", T)


def compare(invm: dict, side: list) -> dict:
    # Only the sidecar records inside the in-VM capture window are compared; the receipt's
    # window is what the in-VM record claims to cover. Earlier/later sidecar connections
    # are reported separately, never silently dropped.
    cap0 = invm.get("capture") if isinstance(invm.get("capture"), dict) else {}
    win = cap0.get("window") or {}
    w0, w1 = win.get("start", 0), win.get("stop", float("inf"))
    side_hosts, outside = {}, {"before_window": 0, "after_window": 0}
    for r in side:
        if not r.get("sni"):
            continue
        if r["ts"] < w0:
            outside["before_window"] += 1; continue
        if r["ts"] > w1:
            outside["after_window"] += 1; continue
        side_hosts.setdefault(r["sni"], []).append(r.get("outcome"))
    invm_hosts = {}
    for d in (invm.get("network", {}).get("outbound_destinations") or []):
        if d.get("port") != 443:
            continue
        names = [n.strip() for n in str(d.get("destination") or "").split("|") if n.strip()]
        for n in names:
            invm_hosts.setdefault(n, []).extend(c.get("chain") for c in d.get("chains") or [])
    only_side = sorted(set(side_hosts) - set(invm_hosts))
    only_vm = sorted(set(invm_hosts) - set(side_hosts))
    both = sorted(set(side_hosts) & set(invm_hosts))
    cap = invm.get("capture") if isinstance(invm.get("capture"), dict) else {}
    verdict = "agree" if not only_side else "in_vm_record_incomplete_or_altered"
    return {
        "sidecar_hosts": {h: len(v) for h, v in side_hosts.items()},
        "sidecar_connections_outside_in_vm_window": outside,
        "in_vm_hosts_443": {h: sorted({str(c) for c in v})[:3] for h, v in invm_hosts.items()},
        "agreement": {"verdict": verdict, "both": both, "sidecar_only": only_side, "in_vm_only": only_vm,
                      "in_vm_declared_complete": cap.get("declared_complete"), "in_vm_lost": (cap.get("kernel_counters_at_stop") or {}).get("lost")},
        "coverage": {"sidecar": "TCP/443 from main container only (Modal relay); no DNS, no other ports; SNI read from ClientHello, no decryption",
                     "in_vm": cap.get("scope")},
    }
