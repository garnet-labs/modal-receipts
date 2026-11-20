"""Build paired-outpost-record.html: Devin's own account of an Outpost session (left) next to the kernel/Sidecar receipt (right).

    python3 outpost_record.py out-outpost
"""
import html, json, sys, time
from pathlib import Path

out = Path(sys.argv[1] if len(sys.argv) > 1 else "out-outpost")
R = json.load(open(out / "receipt.json"))
D = json.load(open(out / "devin-account.json"))
E = [json.loads(l) for l in open(out / "events.jsonl") if l.strip()]
ev = {e["event"]: e for e in E if e["event"] != "worker_log"}
h = html.escape


class Raw(str):
    """Pre-rendered HTML cell; everything else is escaped."""


def fmt_ts(t):
    return time.strftime("%H:%M:%S", time.gmtime(t)) + f".{int((t % 1) * 10):d}"


def clk(u):
    return u[11:] if isinstance(u, str) and u.startswith("2026-10-17T") else u


def tbl(rows, head):
    s = "<table><thead><tr>" + "".join(f"<th>{h(c)}</th>" for c in head) + "</tr></thead><tbody>"
    for r in rows:
        s += "<tr>" + "".join(f"<td>{c if isinstance(c, Raw) else h(str(c))}</td>" for c in r) + "</tr>"
    return s + "</tbody></table>"


cap, agr, side, net, procs, files = R["capture"], R["agreement"], R["sidecar"], R["network"], R["processes"], R["files"]
sess = D["session"]
side_hosts = {x["host"]: x for x in side["hosts"]}
host_rows = []
for host in sorted(set(agr["both"]) | set(agr["sidecar_only"]) | set(agr["in_vm_only"])):
    sh = side_hosts.get(host, {})
    chains = agr["process_by_host"].get(host, [])
    where = "both" if host in agr["both"] else ("Sidecar only" if host in agr["sidecar_only"] else "in-VM only")
    host_rows.append([host, where, sh.get("connections", "–"), f'{sh.get("bytes_down", 0):,}' if sh else "–",
                      Raw("<br>".join(f"<code>{h(c)}</code>" for c in chains) or "<em>no in-VM chain</em>")])

workload_pids = {}
for l in procs["lineage"]:
    a = " ".join(l["argv"])
    if any(k in a for k in ("git clone https://github.com/garnet-labs/modal-receipts", "git clone https", "py_compile sidecar", "npm init", "npm install left-pad", "git-remote-https origin https://git-manager")):
        workload_pids[l["pid"]] = l
wl_rows = [[l["pid"], l["ppid"], Raw(f'<code>{h(l["chain"])}</code>'), Raw(f'<code>{h(" ".join(l["argv"])[:140])}</code>')] for l in sorted(workload_pids.values(), key=lambda x: x["pid"])]

# hand-read from Devin's event timestamps for the one recorded session; any other session gets "not computed"
SAMPLE_TIMINGS = {"devin-85ca56e38aee4ec894263fd673552650": [
    ("session create → claimed", "≈2.2 s", "API create 00:42:28.8 → queue phase claimed 00:42:30.9 (Devin events)"),
    ("claimed → connected", "2.5 s", "00:42:30.9 → 00:42:33.5 (Devin events; devin-remote binary downloaded in between)"),
    ("connected → first command", "1.9 s", "00:42:33.5 → shell_process_started 00:42:35.4"),
    ("first command → Devin says done", "4.6 s", "00:42:35.4 → 00:42:40.0"),
    ("session sleep → worker exit", "≈1 s", "sleep 00:44:10 → remote exited cleanly 00:44:11 (worker ran with --once)"),
]}
timing = [
    ("sandbox create", f'{ev["sandbox_created"]["s"]} s', "Modal Sandbox.create returned"),
    ("Sidecar listening (fail-closed gate)", f'{ev["sidecar_listening"]["s"]} s', "relay accepting on :443 before any workload"),
    ("recorder arm", f'{ev["recorder_armed"]["s"]} s', "audit rules loaded + DNS forwarder up"),
    ("Sandbox.create returned → worker registered", f'{next(e for e in E if e["event"] == "worker_log" and "Worker started!" in e["line"])["t"] - ev["sandbox_created"]["t"]:.1f} s', '"Worker started! Now you can launch sessions" at 00:40:00.9'),
    *SAMPLE_TIMINGS.get(sess["session_id"], [(k, "not computed for this session", "read from Devin's event timestamps by hand for the sample run only")
                                            for k in ("session create → claimed", "claimed → connected", "connected → first command", "first command → Devin says done", "session sleep → worker exit")]),
    ("receipt build", f'{R["outpost"].get("receipt_build_s", "–")} s', "audit parse + Sidecar merge, in the VM"),
    ("Sidecar relay overhead", "not re-measured (n=1)", "earlier series: +1 ms per connection, p50"),
]

doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Paired Outpost record — {h(sess['session_id'])}</title>
<style>
body{{font:14px/1.45 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1b1b1f;margin:0;background:#fafafa}}
header{{padding:20px 28px;border-bottom:1px solid #e3e3e8;background:#fff}} h1{{font-size:20px;margin:0 0 6px}} h2{{font-size:16px;margin:0 0 10px}} h3{{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:#555;margin:18px 0 6px}}
.cols{{display:grid;grid-template-columns:1fr 1fr;gap:20px;padding:20px 28px}} .col{{background:#fff;border:1px solid #e3e3e8;border-radius:8px;padding:16px 18px;min-width:0}}
.tag{{display:inline-block;font-size:11px;padding:2px 7px;border-radius:10px;background:#eef;color:#224;margin-left:6px}} .tag.obs{{background:#e8f5ec;color:#164}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}} th,td{{text-align:left;vertical-align:top;padding:4px 6px;border-bottom:1px solid #eee}} th{{color:#555;font-weight:600}}
code{{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;background:#f3f3f6;padding:1px 3px;border-radius:3px;word-break:break-all}} pre{{font:12px ui-monospace,Menlo,monospace;background:#f3f3f6;padding:8px;border-radius:6px;overflow:auto;white-space:pre-wrap}}
.verdict{{font-size:15px;font-weight:600;padding:8px 10px;border-radius:6px;background:#e8f5ec;color:#164;margin:8px 0}} .muted{{color:#666}} .note{{background:#fff8e1;border:1px solid #f1e2a8;padding:8px 10px;border-radius:6px;font-size:12.5px}}
footer{{padding:16px 28px;color:#666;font-size:12px}}
</style></head><body>
<header><h1>One Devin Outpost session, two accounts</h1>
<div class="muted">Session <a href="{h(sess['url'])}">{h(sess['session_id'])}</a> · outpost pool <code>garnet-receipts</code> · worker = official <code>devin worker start --once</code> inside Modal VM Sandbox <code>{h(R['outpost']['sandbox_id'])}</code> (kernel {h(cap['kernel'])}) · n = 1 · all times UTC 2026-10-17</div>
<p class="note">Left: what Devin reports through its API. Right: what the kernel audit record inside the VM and the Modal Sidecar outside it recorded. Devin's exit code (left) and the recorder's completeness counters (right) are two different claims; each is shown where it comes from.</p></header>
<div class="cols">
<div class="col"><h2>Devin's own account <span class="tag">self-reported · Devin API</span></h2>
<div class="muted">{h(D['source'])}</div>
<h3>Session</h3>
{tbl([[k, v] for k, v in sess.items()], ["field", "value"])}
<h3>Network policy in the queue entry (the claim)</h3>
<pre>{h(json.dumps(D['network_policy_claim'], indent=1))}</pre>
<div class="note">Devin Outposts reference: the policy "comes from the security profile governing the session; enforcing it on your machines is the outpost operator's responsibility." Here it was <b>not enabled</b>, so there was nothing to enforce — the receipt on the right is the only record of what the session actually reached.</div>
<h3>Queue updates (Devin events)</h3>
{tbl([[clk(q['utc']), q['phase'], q['text'] + (f" · acceptor {q['acceptor_id']}" if 'acceptor_id' in q else '')] for q in D['queue_updates']], ["time", "phase", "text"])}
<h3>Messages</h3>
{tbl([[clk(m['utc']), m['from'], m['text']] for m in D['messages']], ["time", "from", "text"])}
<h3>Devin's thoughts (thought_summary events)</h3>
{tbl([[clk(t['utc']), t['text']] for t in D['thoughts']], ["time", "text"])}
<h3>Shell activity Devin reports</h3>
{tbl([[clk(s['utc_started']), clk(s['utc_completed']), f"exit {s['exit_code']}", Raw(f"<code>{h(s['command'])}</code>")] for s in D['shell']], ["started", "completed", "result", "command"])}
<div class="muted">Devin's chain analysis marks each of the {len(D['shell'][0]['chain_certainly_ran'])} sub-commands <code>certainly_ran: true</code>. Output excerpt: <code>{h(D['shell'][0]['output_excerpt'])}</code></div>
<h3>Scope of this account</h3>
<div class="muted">One tool call, its exit code and output, and Devin's messages. Hosts, processes, files and record completeness appear only on the right.</div>
<div class="muted">Other events: {h('; '.join(D['other_events']))}. Total events: {D['event_count']}.</div>
</div>
<div class="col"><h2>Kernel / Sidecar receipt <span class="tag obs">observed · in-VM audit + Modal Sidecar</span></h2>
<div class="verdict">agreement: {h(agr['verdict'])} — {len(agr['both'])} hosts seen by both, {len(agr['sidecar_only'])} Sidecar-only, {len(agr['in_vm_only'])} in-VM-only · kernel lost = {h(str(agr['in_vm_lost']))} · declared complete = {agr['in_vm_declared_complete']}</div>
<div class="muted">{h(agr['meaning'])}</div>
<h3>Capture</h3>
{tbl([["recorder", f"{cap['recorder']} (ruleset {cap['ruleset']}), kernel {cap['kernel']}"],
       ["window", f"{fmt_ts(cap['window']['start'])} → {fmt_ts(cap['window']['stop'])} ({cap['window']['seconds']:.0f} s; armed before the worker started, stopped after it exited)"],
       ["syscall records", f"{cap['syscall_records']:,} across {len(cap.get('log_files', []))} audit log files"],
       ["kernel counters at stop", json.dumps(cap['kernel_counters_at_stop'])],
       ["scope", cap['scope']], ["out of scope", ", ".join(cap['out_of_scope'])],
       ["Sidecar coverage", side['coverage']],
       ["Sidecar", f"{side['connections']} connections, {side['relayed']} relayed, {side['readiness_probes_excluded']} readiness probe excluded, {side['connections_outside_in_vm_window']['before_window']} before / {side['connections_outside_in_vm_window']['after_window']} after the in-VM window"]], ["field", "value"])}
<h3>Outbound hosts, attributed to the chain that opened them</h3>
{tbl(host_rows, ["host (SNI / DNS name)", "seen by", "Sidecar conns", "bytes down", "root-to-action chain (in-VM)"])}
<div class="muted">Chain roots are the Sandbox exec shells; <code>devin</code> is the worker, <code>devin-remote_ca</code> the per-session remote it downloaded. The session's own <code>git clone</code> went to <code>git-manager.devin.ai</code> (Devin rewrote the GitHub URL to its proxy and used a credential-store file it shredded at the end); <code>github.com</code> was reached by devin-remote's own clone of <code>CognitionAI/devin-marketplace</code>; the 208 MB from <code>windsurf-stable.codeiumdata.com</code> is the serve-web bundle fetched by <code>curl</code>.</div>
<h3>Workload lineage (the commands Devin reported, as the kernel saw them)</h3>
{tbl(wl_rows, ["pid", "ppid", "chain", "argv"])}
<div class="muted">pid 1500 is the tool shell (<code>bash -c "cd /tmp && … && npm install left-pad"</code>); bash exec'd into <code>node</code> for its last command, so the pid ends as <code>node</code>. Exit codes are not in the lineage; "all commands succeeded" is Devin's claim (left), consistent with <code>/tmp/modal-receipts/.git</code> and <code>package.json</code> existing in the guest at teardown.</div>
<h3>Processes and files</h3>
{tbl([["processes executed / seen", f"{procs['executed']} / {procs['total_seen']}"], ["paths written", f"{files['paths_touched']:,}"],
       ["by top level", ", ".join(f"{x['prefix']} ({x['paths']})" for x in files['by_top_level'] if x['paths'] > 2)]], ["field", "value"])}
<h3>Measured (n = 1)</h3>
{tbl(timing, ["step", "value", "how"])}
<h3>Record of this record</h3>
<div class="muted">First receipt build read only <code>/var/log/audit/audit.log</code>; auditd had rotated at 8 MB during the session, so the first 160 s were missing and the verdict was <code>in_vm_record_incomplete_or_altered</code>. The recorder was fixed (read rotated files; stop rotating) and the receipt rebuilt in the same still-running VM — that rebuild is what is shown here. The first receipt's summary (2 hosts both, 10 Sidecar-only) is in FACTS.md; its file was overwritten by the rebuild.</div>
</div></div>
<footer>Built by <code>outpost_record.py</code> from <code>receipt.json</code>, <code>devin-account.json</code>, <code>events.jsonl</code> (garnet-labs/modal-receipts, branch devin/outpost-node). No security vocabulary is used on purpose: this is a record of what ran, not a judgement.</footer>
</body></html>"""
(out / "paired-outpost-record.html").write_text(doc)
print("wrote", out / "paired-outpost-record.html", len(doc))
