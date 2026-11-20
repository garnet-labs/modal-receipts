"""Finish an outpost_node.py run from a reconnected handle: stop the recorder, build the receipt, collect logs.

    DEVIN_OUTPOSTS_TOKEN=... python3 outpost_finish.py <sandbox_id> <sidecar_container_id> <outpost_id> <session_id> <outdir>
"""
import json, os, sys, time, urllib.request
import modal
from modal.sandbox import SidecarContainer
from sidecar_receipts import merge
from outpost_node import _exec, fleet, redact, SIDECAR_NAME

sandbox_id, sidecar_id, outpost_id, session_id, out = sys.argv[1:6]
token = os.environ["DEVIN_OUTPOSTS_TOKEN"]
os.makedirs(out, exist_ok=True)
sb = modal.Sandbox.from_id(sandbox_id)
sc = SidecarContainer(sb, sidecar_id, SIDECAR_NAME)
t5 = time.monotonic()
rc, running, _ = _exec(sb, "pgrep -fa 'devin [w]orker start' || echo none; pgrep -fa 'devin-[r]emote' || echo none", 30)
print("procs:", running.strip())
print("stop:", _exec(sb, "bash /opt/garnet/recorder.sh stop", 60)[1].strip())
rc, rcpt, err = _exec(sb, "python3 /opt/garnet/receipt.py", 900)
invm = json.loads(rcpt) if rc == 0 else None
print("receipt.py rc", rc, (err or "")[-300:])
rc2, slog, serr = _exec(sc, "cat /garnet/sidecar.log; echo ---ERR; tail -c 1500 /garnet/recorder.err 2>/dev/null", 120)
log_txt, _, err_txt = slog.partition("---ERR")
side = [json.loads(l) for l in log_txt.splitlines() if l.strip().startswith("{")]
print("sidecar rc", rc2, "connections", len(side), "err", err_txt.strip()[-300:], serr[-200:])
entry = None
try:
    entry = fleet(f"/opbeta/outposts/devins/{session_id}", token)
    entry.get("status", {}).pop("connect_token", None)
except Exception as e:
    print("queue entry fetch failed", e)
receipt = merge(invm, side, None if rc == 0 else err[-1500:])
receipt["outpost"] = {"outpost_id": outpost_id, "name": "garnet-receipts", "session_id": session_id, "queue_entry": entry,
                      "worker": "devin worker start --once (Devin CLI, official)", "sandbox_id": sandbox_id, "sidecar_id": sidecar_id,
                      "receipt_build_s": round(time.monotonic() - t5, 2)}
json.dump(receipt, open(f"{out}/receipt.json", "w"), indent=1)
print("verdict", receipt["agreement"]["verdict"], "build_s", receipt["outpost"]["receipt_build_s"])
open(f"{out}/worker.log", "w").write(redact(_exec(sb, "cat /garnet/worker.log", 60)[1]))
open(f"{out}/guest-state.txt", "w").write(_exec(sb, "ls -la /workspace /tmp /tmp/modal-receipts 2>/dev/null | head -80; du -sh /var/log/audit/audit.log; auditctl -s; ls /var/log/devin/ 2>/dev/null", 60)[1])
open(f"{out}/audit.log.gz.b64", "w").write(_exec(sb, "cat $(ls -r /var/log/audit/audit.log.* 2>/dev/null) /var/log/audit/audit.log | gzip -c | base64 -w0", 600)[1])
open(f"{out}/dns.log", "w").write(_exec(sb, "cat /garnet/state/dns.log 2>/dev/null", 60)[1])
open(f"{out}/remote.log", "w").write(redact(_exec(sb, "cat /var/log/devin/remote.log.* 2>/dev/null | head -c 2000000", 120)[1]))
print("done; sandbox left running — terminate separately")
