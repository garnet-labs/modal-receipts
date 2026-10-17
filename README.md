# Every Modal sandbox run gets a receipt, recorded from a Sidecar the sandbox cannot touch

A `modal run` script. It launches Modal **VM Sandboxes** with a **Sandbox Sidecar** named
`garnet` and `experimental_options={"proxy_traffic_via_sidecar": "garnet"}`, so every TCP/443
connection the sandbox opens is relayed by Modal to the Sidecar. The Sidecar reads the host name
from the TLS ClientHello (SNI), passes the bytes through unchanged, and writes one line per
connection. Nothing is decrypted, nothing is installed in the sandbox image, and code running in
the sandbox cannot create, stop or edit the Sidecar.

Each run comes back with one receipt that says:

1. **where it connected**: every outbound HTTPS host, from the Sidecar's record;
2. **which process made each connection**: from an optional in-VM recorder (Linux audit,
   `guest/`), as root-to-action chains such as `bash > node > sh > node`;
3. **whether the two records agree**: if the Sidecar relayed a host the in-VM record lacks, the
   receipt says the in-sandbox record is incomplete or was changed (root in the sandbox can edit
   anything it can reach; it cannot reach the Sidecar);
4. **coverage**, on every receipt: TCP/443 through the relay only. DNS, other ports, UDP, TLS
   without SNI and the Sidecar's own traffic are not covered, and the receipt says so;
5. **what is new across runs**: "24 reached only their group's common hosts, 6 reached something
   new, here is the process", plus the union of hosts as the next run's `outbound_domain_allowlist`,
   so a revised policy constrains the next run and the receipt records what that policy refused.

Zero engineering to try (four lines around `Sandbox.create` you already have); one runtime flag
to ship (the same Sidecar as a platform option).

## Run it

```sh
pip install modal==1.6.2 && modal setup                                   # once
git clone https://github.com/garnet-labs/modal-receipts && cd modal-receipts
modal run sidecar_receipts.py --n 10                                       # 30 VM sandboxes: sidecar / in-VM-only / unrecorded
modal run sidecar_receipts.py --n 30 --out out-sidecar30                   # the n=30 cost table and allowlist
modal run sidecar_receipts.py --workload https --n 6                       # per-connection relay cost, 200 GETs per sandbox
modal run sidecar_receipts.py --n 10 --cells sidecar \
   --allowlist out-sidecar30/allowlist.json --constructed 1               # evidence-derived allowlist rerun (+1 constructed refusal)
modal run sidecar_probe.py                                                 # 1 sandbox: fail-closed, agree, tamper rerun
```

The package list is the real top-of-registry install cohort in `cohorts.py` (npm + PyPI); nothing
in it is constructed. The one constructed case is labelled `constructed:` in every output.

## The four lines a customer adds

```python
sb = modal.Sandbox.create("sleep", "infinity", app=app, image=image, runtime="vm", memory=3072,
    experimental_options={"proxy_traffic_via_sidecar": "garnet", "vm_sidecar_memory_reserve_mib": 1024})
sb._experimental_sidecars.create("python", "-u", "/recorder.py", name="garnet", image=garnet_image,
    experimental_memory_reserve_consume_mib=512,
    outbound_domain_allowlist=[...])   # optional: Modal enforces it on SNI; see "Allowlist" below
```

Until the Sidecar is listening, HTTPS from the sandbox is refused by Modal (fail-closed; observed
as `curl: (35) SSL_ERROR_SYSCALL` in 3 of 3 probe runs). `sidecar/recorder.py` is 120 lines of
asyncio: accept on :443, read the ClientHello, record `{ts, client, sni, upstream, outcome,
bytes_up, bytes_down, duration}`, relay both directions.

## What the 30-install cohort said (2026-10-16, n=30 per cell, `samples/sidecar/install-n30/`)

```
Agreement (sidecar cell, n=30): agree=30
npm: common hosts (>=90% of 20 runs): registry.npmjs.org
pip: common hosts (>=90% of 10 runs): files.pythonhosted.org, pypi.org
24 runs reached only their group's common hosts; 6 reached something new
- sqlite3     github.com, release-assets.githubusercontent.com   via bash > node > sh > node
- serverless  install.serverless.com                            via bash > node > sh > node
- puppeteer   storage.googleapis.com                            via bash > node > sh > node
- canvas      github.com, release-assets.githubusercontent.com   via bash > node > sh > node
- cypress     cdn.cypress.io, download.cypress.io               via bash > node > sh > node
- node-sass   github.com, nodejs.org                            via bash > node > sh > node > node
Evidence-derived allowlist (union of relayed hosts over 30 real runs): cdn.cypress.io, download.cypress.io,
  files.pythonhosted.org, github.com, install.serverless.com, nodejs.org, pypi.org, registry.npmjs.org,
  release-assets.githubusercontent.com, storage.googleapis.com
```

The host list comes from the Sidecar (the record the sandbox cannot edit); the process chain
comes from the in-VM record; "agree" means every host the Sidecar relayed inside the in-VM capture
window also appears in the in-VM record. 271 relayed connections across the 30 sidecar runs
(p50 14 per run); all 90 installs exited 0; `lost 0` in every in-VM record.

## Step 5: a revised policy constrains the next run (`samples/sidecar/allowlist-rerun/`)

The program's one demonstration is: an agent executes a task; the ordinary agent trace misses a
consequential subprocess or outbound connection; Garnet captures it; the verification result
changes a review decision; **a revised policy constrains the next run.** On Modal the last step is
Modal's own control. The union of hosts above (10 hosts, derived from 30 real runs) was passed as
the Sidecar's `outbound_domain_allowlist` and the 10-package subset rerun: **10 of 10 exited 0,
10 of 10 agree.** Each receipt now carries the policy it ran under:

```json
"sidecar": {"policy": {"outbound_domain_allowlist": ["cdn.cypress.io", "..."],
                       "source": "evidence-derived: union of Sidecar-relayed hosts over 30 real runs (allowlist.json)",
                       "enforced_by": "Modal, on the Sidecar's outbound connections, matched on TLS ClientHello SNI"}}
```

One **constructed** case was added: `curl https://example.com` from the sandbox, a host outside the
union. The receipt records it as **refused by policy, with the policy source stated**: the Sidecar
opened the upstream TCP connection, sent the 517-byte ClientHello, received 0 bytes back; curl failed
with `(35) SSL_ERROR_SYSCALL`.

```json
{"host": "example.com", "connections": 1, "relayed": 0, "bytes_up": 517, "bytes_down": 0,
 "outcomes": {"refused_by_policy": 1},
 "policy_source": "sidecar.outbound_domain_allowlist (evidence-derived: union of Sidecar-relayed hosts over 30 real runs)"}
```

The same constructed step with no allowlist on the Sidecar was relayed and returned 200
(`samples/sidecar/constructed-no-allowlist/`), so the refusal is Modal's SNI match on the Sidecar's
allowlist, and a refused host is visible in the receipt, not silent.

One further run (`allowlist-rerun-main-cidr-empty/`, n=2 + 2 constructed): the main container also
got `outbound_cidr_allowlist=[]`, which Modal's docs allow next to the relay. Installs still pass
through the relay; a constructed `curl http://example.com:80` times out (`rc=28`), refused by
Modal before it reaches anything (it never appears in the Sidecar record, which the coverage line
says). In that shape every permitted egress except DNS goes through the Sidecar.

## The receipt (one per run, `receipts/run-NNN-sidecar-<package>.json`)

```json
{
 "schema": "garnet.sandbox-receipt/0.2",
 "capture":  {"recorder": "linux-audit", "ruleset": "nofiles", "kernel": "7.2.9",
              "kernel_counters_at_stop": {"enabled": "1", "lost": "0"}, "declared_complete": true,
              "window": {"start": 1760640001.2, "stop": 1760640006.9}, "scope": "...", "out_of_scope": ["..."]},
 "processes": {"lineage": [{"comm": "node", "argv": ["node", "install.mjs"], "chain": "bash > node > sh > node"}]},
 "network":  {"outbound_destinations": [{"destination": "storage.googleapis.com", "port": 443,
              "chains": [{"chain": "bash > node > sh > node", "connections": 2}]}]},
 "sidecar":  {"recorder": "garnet-sidecar-sni-relay", "name": "garnet", "connections": 17, "relayed": 17,
              "hosts": [{"host": "registry.npmjs.org", "connections": 15, "relayed": 15, "bytes_up": 41213, "bytes_down": 9431520},
                        {"host": "storage.googleapis.com", "connections": 2, "relayed": 2}],
              "connections_outside_in_vm_window": {"before_window": 0, "after_window": 0},
              "coverage": "TCP/443 leaving the main container, relayed by Modal to the Sidecar; host name read from the TLS ClientHello SNI, nothing decrypted. Not covered: DNS, any other port, UDP, TLS without SNI (refused, recorded as refused_no_sni), traffic from the Sidecar itself.",
              "original_destination_visible": false},
 "agreement": {"verdict": "agree", "both": ["registry.npmjs.org", "storage.googleapis.com"], "sidecar_only": [], "in_vm_only": [],
               "in_vm_declared_complete": true, "in_vm_lost": "0",
               "process_by_host": {"storage.googleapis.com": ["bash > node > sh > node"]}}
}
```

`agreement.verdict` is `in_vm_record_incomplete_or_altered` whenever the Sidecar relayed a host
inside the in-VM window that the in-VM record lacks. `samples/sidecar/probe-tamper.json` is the
same sandbox twice: once as recorded (`agree`), once after root in the sandbox deleted the
`connect`/SOCKADDR lines from `/var/log/audit/audit.log` (1047 -> 774 lines). The in-VM record still
says `declared_complete: true, lost: 0` because it cannot see its own edit; the verdict flips
because the Sidecar's record did not change.

Known detail in the current samples: each receipt lists one `(no SNI)` connection with outcome
`refused_no_sni`. That is the driver's own readiness check (`echo > /dev/tcp/127.0.0.1/443` from
inside the Sidecar), not sandbox traffic; the driver now excludes it as `readiness_probes_excluded`.

## Cost (see `ENGINEERING.md` for the tables)

- Sidecar up (create + listening on :443): **p50 0.74 s, p95 1.13 s** (n=30; pooled over all 64
  sidecar runs today: 0.77 / 1.03). Off the sandbox's own cold path if started in parallel.
- Per-connection relay cost: 200 sequential HTTPS GETs with a new TCP connection each, 6 sandboxes
  per cell (n=1200 requests per cell): **p50 0.112 s via the Sidecar vs 0.111 s unrecorded**, p95
  0.155 vs 0.158. About 1 ms at the median; the tails (p99 0.8-2.6 s, max 6-17 s) appear in all
  three cells and are the upstream, not the relay.
- In-VM recorder (optional): arm p50 0.35 s / p95 0.55 s, receipt p50 0.27 s / p95 0.96 s (n=115);
  install workloads paired per package against the unrecorded cell at n=30: median delta -0.17 s
  (sidecar) and -0.21 s (in-VM only), i.e. inside run-to-run noise. Default ruleset is `nofiles`;
  the file rule costs ~25 us per audited write and is opt-in.
- Sandbox create and first exec are unchanged by the Sidecar (0.08 / 0.98 s vs 0.09 / 1.03 s at n=30).

## Devin Outpost worker in the same VM (`outpost_node.py`, `samples/outpost/`)

The same Sidecar + in-VM recorder around the official Devin CLI worker, so a Devin Cloud session that runs on your own machine leaves a receipt:

```
DEVIN_OUTPOSTS_TOKEN=... modal run outpost_node.py --outpost garnet-receipts --max-wait 5400
# then create a session on the pool, e.g. POST /v3/organizations/{org}/sessions {"prompt": ..., "platform": "garnet-receipts"}
```

One long-lived VM Sandbox (ubuntu 24.04 + git/ffmpeg/auditd + Devin CLI) with the `garnet` Sidecar attached; the recorder is armed, then `devin worker start --outpost=<pool> --once` claims one session and exits when it ends. The outpost token enters the sandbox as a `modal.Secret` built from the driver's environment. The driver writes `receipt.json` (in-VM audit + Sidecar, agreement verdict, the queue entry's `network_policy`), `events.jsonl` (timings) and the worker log (token-free). `outpost_record.py` renders `paired-outpost-record.html`: Devin's own account of the session (API events) on the left, the receipt on the right. `outpost_finish.py` finishes a run from a reconnected sandbox handle.

`samples/outpost/` holds the first real run (2026-10-17, n = 1): one Lite session on pool `garnet-receipts` did `git clone` + `py_compile` + `npm install left-pad` and said "done"; the receipt agrees with the Sidecar on 12 hosts (Devin's own binaries, gateway and telemetry included, each attributed to its chain), `lost = 0`. `samples/outpost/FACTS.md` has the numbers and the two bugs the run found (audit log rotation at 8 MB, fixed in `guest/`; the driver's own `pgrep`).

## What this is not

- It is not more than Modal sees host-side. Modal relays the bytes; the Sidecar writes them down
  for the customer, in a format the customer keeps and can compare with the same receipt from a
  GitHub Actions job or their own cluster.
- It is not packet capture or TLS inspection. Hosts are the SNI the sandbox asked for; the original
  destination IP is not forwarded by the relay (`SO_ORIGINAL_DST` returned nothing in 64 of 64 runs,
  as Modal's docs state).
- The in-VM record is optional and demoted to process attribution. On Modal VM guests it is Linux
  audit today (the guest kernel has no FTRACE/KPROBES/BTF for eBPF); the production shape would be
  a cgroup-BPF `connect4` hook plus the proc connector, which the kernel already supports
  (`CONFIG_CGROUP_BPF=y`, `CONFIG_PROC_EVENTS=y`).

Files: `sidecar_receipts.py` (driver, `.map()` fan-out, merge, summary, allowlist), `sidecar/recorder.py`
(the Sidecar), `sidecar_probe.py` (one sandbox, fail-closed + tamper), `guest/` (in-VM recorder and
receipt builder), `cohorts.py`, `receipts.py` (the earlier in-VM-only driver), `samples/sidecar/`
(every output quoted here), `ENGINEERING.md`, `IMPLICATIONS.md`, `NOTE-TO-ERIK.md`, `present.html`.
