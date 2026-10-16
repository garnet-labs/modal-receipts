# The engineering case, measured (Modal VM Sandboxes + Sidecars, 2026-10-16)

Everything below was measured on Modal `runtime="vm"` sandboxes (guest kernel 7.2.9, 2 CPU,
2048 MiB main + 1024 MiB Sidecar reserve in the sidecar cell, 2048 MiB otherwise), workspace
`jadoonf`, `modal==1.6.2`, with the code in this directory. Three cells, same image, same
workload: **sidecar** (Sidecar relay + optional in-VM recorder), **invm** (in-VM recorder only,
the earlier design), **none** (unrecorded). Every number states its n; p50 / p95 are over sandboxes
unless the row says "per request". Raw outputs: `samples/sidecar/`.

## 1. Three numbers

| question | answer | n |
|---|---|---|
| How long until the Sidecar is up? (create + listening on :443, fail-closed until then) | **p50 0.74 s, p95 1.13 s** | 30 (pooled 64: 0.77 / 1.03) |
| What does the relay cost per connection? (new TCP + TLS per request, `registry.npmjs.org/-/ping`) | **p50 0.112 s vs 0.111 s unrecorded (+1 ms); p95 0.155 vs 0.158** | 1200 requests per cell, 6 sandboxes per cell |
| What does the optional in-VM recorder cost? | arm **0.35 / 0.55 s**, receipt **0.27 / 0.96 s**; workload delta vs unrecorded, paired per package: **median -0.17 s** (inside noise) | 115 recorded sandboxes; 30 pairs |

## 2. Start-up, per sandbox (install cohort, n=30 per cell, `install-n30/SUMMARY.md`)

| phase | sidecar | in-VM only | unrecorded |
|---|---|---|---|
| `Sandbox.create()` | 0.08 / 0.32 | 0.14 / 0.44 | 0.09 / 0.30 |
| Sidecar up (create + listening) | 0.73 / 1.13 | - | - |
| first `exec` round-trip | 0.98 / 1.75 | 1.08 / 1.76 | 1.03 / 1.45 |
| arm in-VM recorder (auditd, 4 rules, DNS forwarder) | 0.31 / 0.51 | 0.40 / 0.57 | - |
| workload (one real `npm`/`pip` install) | 3.05 / 36.1 | 3.02 / 32.4 | 3.50 / 40.2 |
| build in-VM receipt | 0.25 / 1.51 | 0.44 / 0.96 | - |
| collect Sidecar log | 0.08 / 0.36 | - | - |
| total | 6.01 / 38.5 | 5.61 / 35.3 | 4.52 / 41.9 |

Reading: the Sidecar adds ~0.75 s once per sandbox, and it is started after `create` returns so it
overlaps the first exec in a real integration (the driver measures it serially). `create` and
first exec are unchanged. The workload p95s are the cohort's two slow packages (cypress, canvas),
present in all three cells. The n=10 table (`install-n10/SUMMARY.md`) agrees: Sidecar up 0.76 / 1.10.

## 3. Per-connection relay cost (`https-relay-cost/SUMMARY.md`)

`workload-https.sh`: 200 sequential `curl --no-keepalive` GETs per sandbox, each a fresh TCP
connection and TLS handshake, 6 sandboxes per cell, seconds per request.

| cell | requests | p50 | p90 | p95 | p99 | mean | non-200 |
|---|---|---|---|---|---|---|---|
| unrecorded | 1200 | 0.111 | 0.137 | 0.158 | 2.60 | 0.189 | 0 |
| in-VM only | 1200 | 0.106 | 0.129 | 0.148 | 1.34 | 0.144 | 0 |
| sidecar | 1200 | 0.112 | 0.136 | 0.155 | 0.76 | 0.179 | 0 |

TCP connect time from the sandbox's view is 2-3 ms in every cell (it connects to the relay, not
the host). The relay is a single asyncio process in the Sidecar doing a blocking-free
`open_connection` per flow and a `getaddrinfo` for the SNI host; at the median it is not visible
above run-to-run noise. The tail (requests above 0.3 s: 1-10 per sandbox in every cell, maxima
6-17 s) is the registry, not the relay: it occurs in the unrecorded cell at the same rate. An
earlier 3-sandbox run (`out-https`, n=600 per cell) showed p95 0.415 via Sidecar vs 0.175, driven by
two sandboxes that hit the same stalls; at n=1200 the p95s converge. Not measured: concurrent
connections (the install workloads open up to 17 per run and showed no delta), large downloads
(bytes relayed per run were up to ~10 MB without a measurable cost), and long-lived streams.

## 4. The in-VM recorder, now optional

The in-VM recorder exists for one thing the Sidecar cannot do: say which process chain made each
connection. It costs arm + receipt (~0.6 s per sandbox, p95 1.4 s, n=115) and, with the default
`nofiles` ruleset (connect/execve/clone/exit_group), no measurable workload time at n=30. The
file-write rule stays opt-in (`GARNET_RULES=full`); earlier micro-benchmarks put it at ~25 us per
audited write, +8 to +40 % on install-heavy steps, and the receipt declares `file writes` out of
scope when it is off.

Why Linux audit: the VM guest kernel ships `CONFIG_AUDIT`/`AUDITSYSCALL` but not FTRACE, KPROBES
or BTF, so eBPF tracing recorders (Jibril attaches 0 of 76 programs) cannot run inside the guest.
Audit has built-in loss accounting (`lost 0` in all 115 recorded sandboxes today at
`backlog_limit 65536`), which is why coverage is declared rather than assumed. The production shape
for the in-VM half is a cgroup-BPF `connect4`/`sendmsg` hook plus the proc connector (both
available: `CONFIG_CGROUP_BPF=y`, `CONFIG_PROC_EVENTS=y`), with no per-write cost and no resolv.conf
change; that is a runtime-option conversation, not something customers put in images.

## 5. Agreement and the tamper check (`probe-tamper.json`)

The comparison is windowed: only Sidecar connections whose timestamp falls inside the in-VM
capture window (`capture.window.start..stop`) are compared; the rest are counted in
`connections_outside_in_vm_window` (the probe's own pre-arm `curl` shows up there as
`before_window: 1`). Same sandbox, `npm install puppeteer`:

- as recorded: Sidecar `registry.npmjs.org` x15, `storage.googleapis.com` x2; in-VM the same two
  hosts via `bash > node` and `bash > node > sh > node`; verdict `agree`.
- after root in the sandbox deleted the SOCKADDR/`connect` lines from `/var/log/audit/audit.log`
  (1047 -> 774 lines): the in-VM record still reports `declared_complete: true, lost: 0`; the
  verdict is `in_vm_record_incomplete_or_altered` with `sidecar_only: [registry.npmjs.org,
  storage.googleapis.com]`.

What the check does not do: it cannot tell "incomplete" from "altered" (both look the same from
outside), and it says nothing about connections the relay does not carry (coverage line).

## 6. Allowlist, from evidence to Modal's control (`allowlist-rerun/`, `allowlist-rerun-main-cidr-empty/`, `constructed-no-allowlist/`)

Union of relayed hosts over the 30 real runs (10 hosts) -> Sidecar created with
`outbound_domain_allowlist=<union>` -> 10 real installs rerun: 10 of 10 exit 0, 10 of 10 `agree`,
Sidecar up 0.69 / 1.01 s (n=10).

Each receipt in that run carries `sidecar.policy` (the list, its source "evidence-derived: union
of Sidecar-relayed hosts over 30 real runs", and `enforced_by` Modal on SNI). This is step 5 of the
program's demonstration: a revised policy constrains the next run.

Constructed (labelled so in every output): `curl https://example.com` from the sandbox with the
allowlist on. Sidecar record: upstream TCP opened to 172.66.147.243, 517 B sent (the ClientHello),
0 B returned, curl `(35) SSL_ERROR_SYSCALL`; recorded as `outcomes.refused_by_policy: 1` with
`policy_source: sidecar.outbound_domain_allowlist (evidence-derived ...)`. Same step with no
allowlist: relayed, 200. Modal matches the Sidecar's allowlist on SNI after the connection opens;
the receipt shows the attempt in both cases, so a refused host is visible, not silent. (The
classification rule: under a Sidecar allowlist, a host outside the list whose upstream connection
opened, sent bytes and received none is `refused_by_policy`; `mark_refused_by_policy` in the driver.)

Main container `outbound_cidr_allowlist=[]` next to the relay (allowed by Modal's docs): 2 of 2
installs pass through the relay; constructed `curl http://example.com:80` times out (`rc=28`),
refused by Modal and never reaching the Sidecar. In that shape everything the platform lets out
except DNS passes through the Sidecar. Tested for port 80 only; other ports/UDP per Modal's docs,
not measured here.

## 7. Concurrency and spend

90 sandboxes (30 per cell) in 108 s wall through one `.map()`; 30 Sidecars created in parallel,
every receipt complete. Today's total: 170 VM sandboxes, 2227 sandbox-seconds (~37 min), 64 of them
with a Sidecar. ASSUMPTION on price: at Modal's published CPU/memory rates that is well under
$1 of sandbox time.

## 8. What this is not

- Not more than the platform's host-side view: Modal relays the bytes and could write the same
  line; the Sidecar writes it for the customer, in the customer's account, in a format shared with
  other substrates.
- Not TLS inspection: nothing is decrypted; a host is the SNI the client sent. TLS without SNI is
  refused by this relay and recorded as `refused_no_sni` (a policy choice; pass-through without a
  name is possible but then the receipt would carry an unnamed connection).
- Not the original destination: the relay does not forward it (`SO_ORIGINAL_DST` empty in 64 of 64
  runs), so a client that pins an IP and sends a different SNI is recorded under the SNI. This is
  the same limit Modal's own `outbound_domain_allowlist` has.
- Not DNS, not other ports, not UDP, not the Sidecar's own traffic. Every receipt says so.
