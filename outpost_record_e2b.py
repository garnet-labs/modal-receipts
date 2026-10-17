"""paired-outpost-record-e2b.html: Devin's own account (left) next to the Jibril profile recorded inside the E2B guest (right)."""
import html, json, sys
from pathlib import Path
out = Path(sys.argv[1] if len(sys.argv) > 1 else "out-e2b")
P = json.load(open(out / "jibril.profile.json")); D = json.load(open(out / "devin-account.json")); R = json.load(open(out / "run.json"))
E = [json.loads(l) for l in open(out / "events.jsonl") if l.strip()]
ev = {e["event"]: e for e in E if e["event"] != "worker_log"}
h = html.escape
class Raw(str):
    """Pre-rendered HTML cell; everything else is escaped."""
def tbl(rows, head):
    s = "<table><thead><tr>" + "".join(f"<th>{h(c)}</th>" for c in head) + "</tr></thead><tbody>"
    for r in rows: s += "<tr>" + "".join(f"<td>{c if isinstance(c, Raw) else h(str(c))}</td>" for c in r) + "</tr>"
    return s + "</tbody></table>"
eb = R["jibril_status_at_ready"]["ebpf"]; sess = D["session"]
peers = P["network"]["egress"]["peers"]; byhost = {}
for p in peers:
    for n in p.get("remote_names") or [p["remote_address"]]:
        d = byhost.setdefault(n, {"conns": 0, "addrs": set(), "ports": set(), "chains": set()})
        d["conns"] += 1; d["addrs"].add(p["remote_address"]); d["ports"].update(p.get("remote_ports", []))
        for t in p.get("proc_trees", []): d["chains"].add(" > ".join(t["ancestry"]))
rows = [[n, d["conns"], ", ".join(sorted(d["ports"])), ", ".join(sorted(d["addrs"])), Raw("<br>".join(f"<code>{h(c)}</code>" for c in sorted(d["chains"])) or "<em>none</em>")] for n, d in sorted(byhost.items())]
tel = P["telemetry"]["network"]["egress"]
timing = [("Sandbox.create", f'{ev["sandbox_created"]["s"]} s'), ("guest setup (Devin CLI + Jibril download)", f'{ev["guest_setup"]["s"]} s'),
          ("Jibril start → 72/76 attached", f'{ev["jibril_ready"]["s"]} s'), ("worker start → registered", f'{ev["worker_registered"]["s_since_start"]} s'),
          *({"devin-d7fac4db7cf449668cf49afe52d79539": [("session create → Devin done", "33 s (01:16:45 → 01:17:18; includes a disk-full retry)"), ("sleep → worker exit", "≈6 s")]}
            .get(sess["session_id"], [("session create → Devin done", "not computed for this session"), ("sleep → worker exit", "not computed for this session")])), ("profile collected", f'{ev["profile_collected"]["s"]} s')]
doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Paired Outpost record (E2B / Jibril) — {h(sess['session_id'])}</title>
<style>body{{font:14px/1.45 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1b1b1f;margin:0;background:#fafafa}}header{{padding:20px 28px;border-bottom:1px solid #e3e3e8;background:#fff}}h1{{font-size:20px;margin:0 0 6px}}h2{{font-size:16px;margin:0 0 10px}}h3{{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:#555;margin:18px 0 6px}}.cols{{display:grid;grid-template-columns:1fr 1fr;gap:20px;padding:20px 28px}}.col{{background:#fff;border:1px solid #e3e3e8;border-radius:8px;padding:16px 18px;min-width:0}}.tag{{display:inline-block;font-size:11px;padding:2px 7px;border-radius:10px;background:#eef;color:#224;margin-left:6px}}.tag.obs{{background:#e8f5ec;color:#164}}table{{border-collapse:collapse;width:100%;font-size:12.5px}}th,td{{text-align:left;vertical-align:top;padding:4px 6px;border-bottom:1px solid #eee}}th{{color:#555;font-weight:600}}code{{font:12px ui-monospace,Menlo,monospace;background:#f3f3f6;padding:1px 3px;border-radius:3px;word-break:break-all}}pre{{font:12px ui-monospace,Menlo,monospace;background:#f3f3f6;padding:8px;border-radius:6px;overflow:auto;white-space:pre-wrap}}.verdict{{font-size:15px;font-weight:600;padding:8px 10px;border-radius:6px;background:#e8f5ec;color:#164;margin:8px 0}}.muted{{color:#666}}.note{{background:#fff8e1;border:1px solid #f1e2a8;padding:8px 10px;border-radius:6px;font-size:12.5px}}footer{{padding:16px 28px;color:#666;font-size:12px}}</style></head><body>
<header><h1>One Devin Outpost session on E2B Embed, two accounts</h1>
<div class="muted">Session <a href="{h(sess['url'])}">{h(sess['session_id'])}</a> · outpost pool <code>garnet-receipts</code> · worker = official <code>devin worker start --once</code> inside E2B sandbox <code>{h(R['sandbox_id'])}</code> (template <code>{h(R['template'])}</code>, operator kernel 6.18.36 built from E2B's config + MODULES/BPF_JIT/FTRACE_SYSCALLS/KPROBES) · recorder = Jibril {h(R['jibril_status_at_ready']['version'])} in the guest · n = 1 · times UTC 2026-10-17</div>
<p class="note">Left: what Devin reports through its API. Right: what Jibril recorded from the guest kernel. Devin's exit codes (left) and Jibril's loader counters (right) are two different claims; each is shown where it comes from.</p></header>
<div class="cols"><div class="col"><h2>Devin's own account <span class="tag">self-reported · Devin API</span></h2><div class="muted">{h(D['source'])}</div>
<h3>Session</h3>{tbl([[k, v] for k, v in sess.items()], ["field", "value"])}
<h3>Network policy in the queue entry (the claim)</h3><pre>{h(json.dumps(D['network_policy_claim'], indent=1))}</pre>
<h3>Messages</h3>{tbl([[m['utc'][11:], m['from'], m['text']] for m in D['messages']], ["time", "from", "text"])}
<h3>Shell activity Devin reports</h3>{tbl([[s['utc'], f"exit {s['exit_code']}", Raw(f"<code>{h(s['command'])}</code>"), s['note']] for s in D['shell']], ["time", "result", "command", "note"])}
<h3>Scope of this account</h3><div class="muted">Tool calls, exit codes, output excerpts and messages. Hosts, process ancestry and loader coverage appear only on the right. Total events: {D['event_count']}.</div></div>
<div class="col"><h2>Jibril profile <span class="tag obs">observed · eBPF in the guest</span></h2>
<div class="verdict">eBPF loader: {eb['programs']} programs, {eb['attached']} attached, {eb['live_links']} live links, errors load {eb['errors']['load']} / attach {eb['errors']['attach']} / link {eb['errors']['link']} · status {h(str(eb.get('status', 'ok')))}</div>
<div class="muted">Recorded with <code>GARNET_SAR=true</code>: no agent registration, the profile stayed in the guest and was pulled by the driver after SIGINT. The 4 unattached programs are the <code>fentry/__sys_connect_file / sock_alloc_file / sock_sendmsg / sock_recvmsg</code> alternates to the <code>security_socket_*</code> hooks that did attach.</div>
<h3>Egress</h3>{tbl([["domains", tel['total_domains']], ["connections", tel['total_connections']], ["profile uuid", P['uuid']], ["profile timestamp", P['timestamp']]], ["field", "value"])}
<h3>Outbound peers with process ancestry</h3>{tbl(rows, ["remote name", "conns", "ports", "addresses", "ancestry (Jibril proc_trees)"])}
<div class="muted"><code>events.e2b.local</code> is E2B's own guest telemetry endpoint (envd → host); everything else is the Devin worker/remote, its plugin and serve-web downloads, and the session's clone (via <code>git-manager.devin.ai</code>) and <code>npm install</code>.</div>
<h3>Measured (n = 1)</h3>{tbl(timing, ["step", "value"])}
<h3>Record of this record</h3><div class="muted">Run 1 (sandbox icweufpmpag29u798hex2) produced an empty profile: the 2.4 GB guest rootfs filled up (Jibril's raw event log + Devin's serve-web bundle) and Jibril could not write <code>jibril.profile.json</code>. Run 2 dropped the raw-event printer; the disk was still 100 % full when Devin ran (its first tool call exited 228, it deleted the bundle and retried) and the profile was written. The rootfs size is a template attribute E2B's <code>min_free_disk_mb</code> did not change here.</div>
</div></div>
<footer>Built by <code>outpost_record_e2b.py</code> from <code>jibril.profile.json</code>, <code>devin-account.json</code>, <code>run.json</code>, <code>events.jsonl</code> (garnet-labs/modal-receipts, branch devin/outpost-node).</footer></body></html>"""
(out / "paired-outpost-record-e2b.html").write_text(doc); print("wrote", out / "paired-outpost-record-e2b.html", len(doc), "peers", len(peers), "hosts", len(rows))
