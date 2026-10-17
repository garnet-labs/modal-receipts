"""A Devin Outpost worker inside one Modal VM Sandbox, with a receipt for the session it serves.

    DEVIN_OUTPOSTS_TOKEN=... modal run outpost_node.py --outpost garnet-receipts --max-wait 5400

The sandbox runs `devin worker start --outpost <name> --once` (the official Devin CLI). Around it:
  - a Sandbox Sidecar named `garnet` relays every TCP/443 connection the sandbox opens and records the
    TLS SNI host name (nothing decrypted; the sandbox cannot reach the Sidecar);
  - the in-VM recorder (guest/recorder.sh: Linux kernel audit + DNS forwarder) attributes each connection,
    process and file write to its root-to-action chain.
When the worker exits (session over) the receipt is built and written to --out, together with the queue
entry Devin published for the session (spec.network_policy) and the worker log (token-free).
The outpost token reaches the sandbox only as a Modal Secret built from this process's environment.
"""
import json, os, re, time, urllib.request
from pathlib import Path

import modal

from sidecar_receipts import merge, guest_bundle, SIDECAR_NAME, SIDECAR_RESERVE_MIB, SIDECAR_CONSUME_MIB

app = modal.App("garnet-outpost-node")
HERE = Path(__file__).parent
API = "https://api.devin.ai"
PACKAGES = ["git", "curl", "ca-certificates", "auditd", "procps", "python3", "python3-venv", "python3-pip",
            "nodejs", "npm", "ffmpeg", "sudo", "openssh-client", "jq", "unzip", "xz-utils"]
worker_image = (modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
                .env({"DEBIAN_FRONTEND": "noninteractive", "HOME": "/root"})
                .apt_install(*PACKAGES)
                .run_commands("curl -fsSL https://cli.devin.ai/install.sh -o /tmp/devin-install.sh && (bash /tmp/devin-install.sh </dev/null || true) && test -x /root/.local/bin/devin",  # installer exits 1 after a login prompt it cannot show
                              "ln -sf /root/.local/bin/devin /usr/local/bin/devin && devin --version",
                              "mkdir -p /workspace/repos && git clone -q https://github.com/garnet-labs/modal-receipts /workspace/repos/modal-receipts"))
sidecar_image = (modal.Image.debian_slim(python_version="3.12")
                 .add_local_file(HERE / "sidecar" / "recorder.py", "/recorder.py", copy=True))
MAIN_MEMORY_MIB = 4096


@app.function(image=worker_image)
def worker_ready(): return "ok"


@app.function(image=sidecar_image)
def sidecar_ready(): return "ok"


def _exec(c, cmd, timeout=60):
    p = c.exec("bash", "-lc", cmd, timeout=timeout)
    out, err = p.stdout.read(), p.stderr.read()
    p.wait()
    return p.returncode, out, err


def fleet(path, token):
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def redact(text):
    return re.sub(r"(cog_|co)[A-Za-z0-9_\-]{40,}", "<token>", text)


@app.local_entrypoint()
def main(outpost: str = "garnet-receipts", out: str = "out-outpost", max_wait: int = 5400, rules: str = "full",
         cpu: int = 4, poll: int = 10):
    token = os.environ.get("DEVIN_OUTPOSTS_TOKEN")
    if not token:
        raise SystemExit("DEVIN_OUTPOSTS_TOKEN is not set in this process's environment")
    outdir = Path(out); outdir.mkdir(parents=True, exist_ok=True)
    events = []

    def ev(event, **kw):
        row = {"t": round(time.time(), 3), "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **kw}
        events.append(row); print(json.dumps(row), flush=True)
        (outdir / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")

    ops = fleet("/opbeta/outposts", token)["items"]
    op = next((o for o in ops if o["spec"]["name"] == outpost or o["metadata"]["outpost_id"] == outpost), None)
    if op is None:
        raise SystemExit(f"outpost {outpost!r} not found; account has: {[o['spec']['name'] for o in ops]}")
    outpost_id = op["metadata"]["outpost_id"]
    ev("outpost_found", outpost_id=outpost_id, name=op["spec"]["name"], platform=op["spec"]["platform"],
       queue_depth=op["status"]["queue_depth"], active_claims=op["status"]["active_claims"])

    t0 = time.monotonic()
    sb = modal.Sandbox.create(
        "sleep", "infinity", app=app, image=worker_image, runtime="vm", cpu=cpu, timeout=max_wait + 1800,
        memory=MAIN_MEMORY_MIB + SIDECAR_RESERVE_MIB, workdir="/workspace",
        secrets=[modal.Secret.from_dict({"DEVIN_OUTPOSTS_TOKEN": token})],
        experimental_options={"proxy_traffic_via_sidecar": SIDECAR_NAME, "vm_sidecar_memory_reserve_mib": SIDECAR_RESERVE_MIB})
    ev("sandbox_created", sandbox_id=sb.object_id, s=round(time.monotonic() - t0, 2))
    sc = None
    receipt = None
    try:
        t1 = time.monotonic()
        sc = sb._experimental_sidecars.create("bash", "-c", "mkdir -p /garnet; exec python -u /recorder.py 2>>/garnet/recorder.err",
                                              name=SIDECAR_NAME, image=sidecar_image, experimental_memory_reserve_consume_mib=SIDECAR_CONSUME_MIB)
        _exec(sc, "until (echo > /dev/tcp/127.0.0.1/443) 2>/dev/null; do sleep 0.05; done; echo up", 120)
        ev("sidecar_listening", sidecar_id=sc.object_id, s=round(time.monotonic() - t1, 2))
        rc, out_, err = _exec(sb, "uname -r; nproc; free -m | awk '/Mem/{print $2}'; devin --version; git --version; ffmpeg -version | head -1", 60)
        ev("guest", rc=rc, out=out_.strip().splitlines(), err=err.strip()[-300:])
        _exec(sb, f"mkdir -p /opt/garnet /garnet && echo '{guest_bundle()}' | base64 -d | tar -xzf - -C /opt/garnet", 60)
        t2 = time.monotonic()
        rc, out_, err = _exec(sb, f"GARNET_RULES={rules} bash /opt/garnet/recorder.sh start", 60)
        ev("recorder_armed", rc=rc, out=out_.strip(), err=err.strip()[-300:], s=round(time.monotonic() - t2, 2))
        t3 = time.monotonic()
        # the worker inherits DEVIN_OUTPOSTS_TOKEN from the sandbox's Modal Secret; nothing on argv
        rc, out_, err = _exec(sb, f"cd /workspace && setsid bash -c 'exec devin worker start --outpost={outpost} --once --poll-interval-secs 5' "
                                  f"</dev/null >/garnet/worker.log 2>&1 & echo $!", 30)
        ev("worker_started", pid=out_.strip(), rc=rc)
        session_id, claimed_at, entry, registered = None, None, None, False
        last_log = ""
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            rc, log, _ = _exec(sb, "cat /garnet/worker.log 2>/dev/null; echo ---RUNNING; pgrep -f 'devin [w]orker start' >/dev/null && echo yes || echo no", 30)
            log, _, running = log.rpartition("---RUNNING")
            if log != last_log:
                new = redact(log[len(last_log):]) if log.startswith(last_log) else redact(log)
                for line in new.strip().splitlines():
                    ev("worker_log", line=line[:400])
                last_log = log
                if not registered and "Worker started!" in log:
                    registered = True
                    ev("worker_registered", s_since_start=round(time.monotonic() - t3, 2))
            q = fleet(f"/opbeta/outposts/devins?outpost={outpost_id}", token)["items"]
            for it in q:
                sid = it["metadata"]["session_id"]
                if session_id is None:
                    session_id = sid
                    ev("session_queued", session_id=sid, phase=it["status"]["phase"], kind=it["spec"]["kind"],
                       network_policy=it["spec"].get("network_policy"))
                if it["status"]["phase"] == "claimed" and claimed_at is None:
                    claimed_at = time.time()
                    ev("session_claimed", session_id=sid, acceptor_id=it["status"].get("acceptor_id"), session_status=it["status"].get("session_status"))
                entry = {k: v for k, v in it.items()}
                entry["status"] = {k: v for k, v in it["status"].items() if k not in ("connect_token",)}
            if running.strip() == "no":
                ev("worker_exited", s_since_start=round(time.monotonic() - t3, 2))
                break
            if session_id and entry and entry["status"].get("session_status") in ("suspended", "terminated"):
                ev("session_status_final", session_status=entry["status"]["session_status"])
            time.sleep(poll)
        else:
            ev("max_wait_reached", session_id=session_id)
            _exec(sb, "pkill -f 'devin worker start'; pkill -f devin-remote; sleep 1", 30)
        if session_id:
            try:
                entry = fleet(f"/opbeta/outposts/devins/{session_id}", token)
                entry.get("status", {}).pop("connect_token", None)
            except Exception as e:  # noqa
                ev("queue_entry_fetch_failed", error=str(e)[:200])
        t5 = time.monotonic()
        _exec(sb, "bash /opt/garnet/recorder.sh stop", 60)
        rc, rcpt, err = _exec(sb, "python3 /opt/garnet/receipt.py", 600)
        invm = json.loads(rcpt) if rc == 0 else None
        rc2, slog, _ = _exec(sc, "cat /garnet/sidecar.log; echo ---ERR; tail -c 1500 /garnet/recorder.err 2>/dev/null", 120)
        log_txt, _, err_txt = slog.partition("---ERR")
        side = [json.loads(l) for l in log_txt.splitlines() if l.strip().startswith("{")]
        receipt = merge(invm, side, None if rc == 0 else err[-1500:])
        receipt["outpost"] = {"outpost_id": outpost_id, "name": outpost, "session_id": session_id, "queue_entry": entry,
                              "worker": "devin worker start --once (Devin CLI, official)", "sandbox_id": sb.object_id, "sidecar_id": sc.object_id}
        ev("receipt_built", s=round(time.monotonic() - t5, 2), verdict=receipt["agreement"]["verdict"], sidecar_connections=len(side),
           in_vm_complete=(invm or {}).get("capture", {}).get("declared_complete") if invm else None)
        (outdir / "receipt.json").write_text(json.dumps(receipt, indent=1))
        rc, wlog, _ = _exec(sb, "cat /garnet/worker.log", 60)
        (outdir / "worker.log").write_text(redact(wlog))
        rc, alog, _ = _exec(sb, "ls -la /workspace /workspace/repos 2>/dev/null; du -sh /var/log/audit/audit.log; auditctl -s", 60)
        (outdir / "guest-state.txt").write_text(alog)
        rc, audit, _ = _exec(sb, "cat $(ls -r /var/log/audit/audit.log.* 2>/dev/null) /var/log/audit/audit.log | gzip -c | base64 -w0", 300)
        (outdir / "audit.log.gz.b64").write_text(audit)
        rc, dnsl, _ = _exec(sb, "cat /garnet/state/dns.log", 60)
        (outdir / "dns.log").write_text(dnsl)
    finally:
        ev("teardown", total_s=round(time.monotonic() - t0, 1))
        sb.terminate()
    print(f"wrote {outdir}/receipt.json, events.jsonl, worker.log", flush=True)
