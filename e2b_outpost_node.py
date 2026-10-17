"""Devin Outpost worker inside an E2B Embed sandbox on an operator-built kernel, recorded by Jibril.

    set -a; . sdk.env; set +a   # E2B_API_KEY / E2B_API_URL / E2B_SANDBOX_URL from `docker compose exec ready cat /run/e2b/sdk.env`
    DEVIN_OUTPOSTS_TOKEN=... python3 e2b_outpost_node.py --template garnet-outpost --outpost garnet-receipts --out out-e2b --max-wait 3600

Guest: Debian 12 base template rebuilt on the operator kernel (6.18 + MODULES/BPF_JIT/FTRACE_SYSCALLS/KPROBES);
guest-setup.sh installs the official Devin CLI and Jibril v2.17.0; Jibril runs with GARNET_SAR=true (no registration,
record stays in the guest) and writes /var/log/jibril/jibril.profile.json; `devin worker start --once` claims one session.
The outpost token reaches the guest only as the env of the worker command (envd exec env), never on argv.
"""
import argparse, json, os, re, time
from pathlib import Path
from e2b import Sandbox
from e2b.sandbox.commands.command_handle import CommandExitException

HERE = Path(__file__).parent
API = "https://api.devin.ai"


def fleet(path, token):
    import urllib.request
    req = urllib.request.Request(API + path, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def redact(text):
    return re.sub(r"(cog_|co)[A-Za-z0-9_\-]{40,}", "<token>", text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", default="garnet-outpost"); ap.add_argument("--outpost", default="garnet-receipts")
    ap.add_argument("--out", default="out-e2b"); ap.add_argument("--max-wait", type=int, default=3600); ap.add_argument("--poll", type=int, default=10)
    a = ap.parse_args()
    token = os.environ["DEVIN_OUTPOSTS_TOKEN"]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    events = []

    def ev(event, **kw):
        row = {"t": round(time.time(), 3), "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **kw}
        events.append(row); print(json.dumps(row), flush=True)
        (out / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\n")

    def run(cmd, timeout=120, **kw):
        try:
            r = sb.commands.run(cmd, user="root", timeout=timeout, **kw)
        except CommandExitException as e:  # non-zero exit is data here, not an error
            return e.exit_code, e.stdout, e.stderr
        return r.exit_code, r.stdout, r.stderr

    ops = fleet("/opbeta/outposts", token)["items"]
    op = next(o for o in ops if o["spec"]["name"] == a.outpost or o["metadata"]["outpost_id"] == a.outpost)
    outpost_id = op["metadata"]["outpost_id"]
    ev("outpost_found", outpost_id=outpost_id, queue_depth=op["status"]["queue_depth"], active_claims=op["status"]["active_claims"])

    t0 = time.monotonic()
    sb = Sandbox.create(a.template, timeout=min(a.max_wait + 600, 3600))  # Embed caps sandbox timeout at 1 h
    ev("sandbox_created", sandbox_id=sb.sandbox_id, s=round(time.monotonic() - t0, 3))
    try:
        rc, o, e = run("uname -r; nproc; free -m | awk '/Mem/{print $2}'; ls /sys/kernel/btf/vmlinux; ls /sys/kernel/debug/tracing/events/syscalls >/dev/null 2>&1 && echo syscalls-tracefs || echo no-syscalls-tracefs; zcat /proc/config.gz | grep -E '^CONFIG_(BPF_JIT|KPROBES|FTRACE_SYSCALLS|MODULES)=' | tr '\\n' ' '")
        ev("guest", rc=rc, out=o.strip().splitlines(), err=e.strip()[-200:])
        sb.files.write("/opt/garnet/guest-setup.sh", (HERE / "e2b" / "guest-setup.sh").read_text(), user="root")
        sb.files.write("/opt/garnet/jibril.yaml", (HERE / "e2b" / "jibril.yaml").read_text(), user="root")
        t1 = time.monotonic()
        rc, o, e = run("bash /opt/garnet/guest-setup.sh", timeout=600)
        ev("guest_setup", rc=rc, out=o.strip().splitlines()[-4:], err=e.strip()[-400:], s=round(time.monotonic() - t1, 1))
        if rc != 0:
            raise SystemExit("guest setup failed")
        t2 = time.monotonic()
        # envd keeps a foreground exec open while any child holds its pipes, so long-lived processes start as envd background commands
        sb.commands.run("cd /opt/garnet && exec ./jibril --config /opt/garnet/jibril.yaml >/var/log/jibril/jibril.stdout 2>&1", background=True, user="root",
                        envs={"GARNET_SAR": "true"}, timeout=0)
        status, eb = None, {}
        for _ in range(60):  # jibril.status.json = process readiness; ebpf.status.json = loader counts (programs/attached/errors)
            rc, o, e = run("cat /var/run/jibril/jibril.status.json 2>/dev/null; echo; echo ---; cat /var/run/jibril/ebpf.status.json 2>/dev/null", timeout=20)
            a1, _, a2 = o.partition("---")
            if a1.strip().startswith("{"):
                status = json.loads(a1)
            if a2.strip().startswith("{"):
                eb = json.loads(a2); eb = eb.get("ebpf", eb)  # ebpf.status.json nests the loader counts under "ebpf"
                if eb.get("programs"):
                    break
            time.sleep(0.5)
        status = status or {}
        status["ebpf"] = eb
        ev("jibril_ready", s=round(time.monotonic() - t2, 2), status=status.get("status"), version=status.get("version"), programs=eb.get("programs"),
           attached=eb.get("attached"), errors=eb.get("errors"), live_links=eb.get("live_links"), ebpf_status=eb.get("status"))
        if not status or (eb.get("attached") or 0) < 60:
            rc, o, e = run("tail -12 /var/log/jibril/jibril.stdout | cut -c1-300; ls -la /var/run/jibril", timeout=20); ev("jibril_log_tail", lines=o.splitlines(), ebpf_keys=list(eb))
            raise SystemExit("jibril did not attach")
        t3 = time.monotonic()
        run("mkdir -p /workspace", timeout=30)
        sb.commands.run(f"cd /workspace && exec devin worker start --outpost={a.outpost} --once --poll-interval-secs 5 >/var/log/worker.log 2>&1", background=True,
                        user="root", cwd="/workspace", envs={"DEVIN_OUTPOSTS_TOKEN": token, "HOME": "/root"}, timeout=0)
        ev("worker_started")
        session_id, entry, registered, last = None, None, False, ""
        deadline = time.monotonic() + a.max_wait
        while time.monotonic() < deadline:
            rc, log, _ = run("cat /var/log/worker.log 2>/dev/null; echo ---RUNNING; pgrep -f 'devin [w]orker start' >/dev/null && echo yes || echo no", timeout=30)
            log, _, running = log.rpartition("---RUNNING")
            if log != last:
                new = log[len(last):] if log.startswith(last) else log
                for line in redact(new).strip().splitlines():
                    if not re.match(r'\s*"[A-Z0-9_]+": "\[REDACTED\]",?$', line):
                        ev("worker_log", line=re.sub(r"\x1b\[[0-9;]*m", "", line)[:400])
                last = log
                if not registered and "Worker started!" in log:
                    registered = True; ev("worker_registered", s_since_start=round(time.monotonic() - t3, 2))
            for it in fleet(f"/opbeta/outposts/devins?outpost={outpost_id}", token)["items"]:
                sid = it["metadata"]["session_id"]
                if session_id is None:
                    session_id = sid
                    ev("session_queued", session_id=sid, phase=it["status"]["phase"], kind=it["spec"]["kind"], network_policy=it["spec"].get("network_policy"))
                entry = dict(it); entry["status"] = {k: v for k, v in it["status"].items() if k != "connect_token"}
            if running.strip() == "no" and registered:
                ev("worker_exited", s_since_start=round(time.monotonic() - t3, 2)); break
            time.sleep(a.poll)
        else:
            ev("max_wait_reached", session_id=session_id)
            run("pkill -f 'devin [w]orker start'; pkill -f devin-remote; sleep 1", timeout=30)
        t5 = time.monotonic()
        rc, o, _ = run("df -h / | tail -1; pkill -INT -x jibril; for i in $(seq 1 120); do pgrep -x jibril >/dev/null || break; sleep 0.5; done; ls -la /var/log/jibril", timeout=120); ev("jibril_stopped", out=o.strip().splitlines())
        rc, prof, _ = run("cat /var/log/jibril/jibril.profile.json", timeout=120)
        rc2, st, _ = run("cat /var/run/jibril/jibril.status.json 2>/dev/null; echo; tail -c 1200 /var/log/jibril/jibril.stdout", timeout=60)
        ev("profile_collected", s=round(time.monotonic() - t5, 2), bytes=len(prof), rc=rc)
        (out / "jibril.profile.json").write_text(prof)
        (out / "jibril.status-and-tail.txt").write_text(st)
        rc, wl, _ = run("cat /var/log/worker.log", timeout=60)
        (out / "worker.log").write_text(redact(wl))
        rc, gs, _ = run("ls -la /workspace /root /root/modal-receipts 2>/dev/null | head -60; df -h /", timeout=60)
        (out / "guest-state.txt").write_text(gs)
        json.dump({"outpost_id": outpost_id, "name": a.outpost, "session_id": session_id, "queue_entry": entry, "sandbox_id": sb.sandbox_id,
                   "template": a.template, "worker": "devin worker start --once (Devin CLI, official)", "jibril_status_at_ready": status},
                  open(out / "run.json", "w"), indent=1)
    finally:
        ev("teardown", total_s=round(time.monotonic() - t0, 1))
        sb.kill()


if __name__ == "__main__":
    main()
