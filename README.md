# Every sandbox run gets a receipt

A `modal run` script. It launches Modal **VM Sandboxes** (`runtime="vm"`) from one
image, runs one real dependency install per sandbox (the thing every coding agent
does all day), fans out with `.map()`, and returns one **execution receipt per run**:

- process lineage (every `execve`, with argv, as root-to-action chains),
- every outbound connection, attributed to the process chain that made it, named
  by the sandbox's own DNS answers,
- files created / written / removed,
- **coverage declared by the kernel**, not by us: the audit subsystem's own
  `enabled` / `lost` / `backlog_limit` counters and the exact rule set, so each
  receipt says whether it saw everything in scope.

Then it tells you which runs contacted only the common hosts and which contacted
something else, and what the recorder cost, measured on the same cohort with and
without it. Nothing leaves your account; receipts come back to your terminal and `./out/`.

## Run it

```sh
pip install modal && modal setup                      # once
git clone <this repo> && cd <this repo>
modal run receipts.py --limit 10                      # ~1 minute, 10 VM sandboxes
modal run receipts.py                                 # 100 installs, 60 npm + 40 PyPI top packages
modal run receipts.py --workload swebench --limit 10  # SWE-bench Lite rollouts in the official images
modal run receipts.py --workload bench --bench-each 10   # recorder cost, recorded vs unrecorded
```

Nothing in the default cohort is constructed. The package list is `cohorts.py`.

## What the 100-install cohort said (2026-10-16)

```
94 runs contacted only their group's common hosts (npm: registry.npmjs.org, pip: pypi.org | files.pythonhosted.org).
6 contacted something new:
- puppeteer   storage.googleapis.com:443                       via bash > node > sh > node
- cypress     cdn.cypress.io | download.cypress.io:443         via bash > node > sh > node
- sqlite3     github.com, release-assets.githubusercontent.com via bash > node > sh > node
- canvas      github.com, release-assets.githubusercontent.com via bash > node > sh > node
- node-sass   github.com, nodejs.org                           via bash > node > sh > node > node
- serverless  install.serverless.com:443                       via bash > node > sh > node
```

None of these is wrong. All of them are postinstall scripts fetching binaries, and all
of them are what goes in `outbound_domain_allowlist` that nobody knew to put there.
Two installs exited non-zero and their receipts are complete anyway: `fsevents` (macOS-only
package, refuses Linux) and `better-sqlite3` (node-gyp build failed on the image's Node 18).
Workload outcome and capture are reported separately, always.
Full output: `samples/install/SUMMARY.md`, one receipt per package in `samples/install/receipts/`.

## What is in the image

Only Modal primitives and stock Ubuntu packages:

```
ubuntu:24.04 + git curl auditd nodejs npm python3   (+ guest/, five small files, copied in at start)
```

- `guest/recorder.sh` arms the Linux kernel audit subsystem (`auditctl` rules on
  `connect`, `execve`, `clone`, `exit_group`, open-for-write, `unlink`/`rename`) and
  starts a 90-line DNS forwarder on `127.0.0.1:53` that logs the answers the sandbox's
  resolver returns. `GARNET_RULES=nofiles` drops the file rules (see cost).
- `guest/workload-install.sh`, `workload-swebench.sh`, `workload.sh`, `workload-bench.sh`
  are the workloads. Real network, no keys.
- `guest/receipt.py` reads `/var/log/audit/audit.log` and the DNS log and writes the
  receipt. It infers nothing: a chain is the recorded parent path of the process that
  called `connect()`.

`receipts.py` is one Modal function (`run_one`) that creates a VM Sandbox, arms, runs,
stops, collects, terminates; the local entrypoint calls `run_one.map(specs)` and
aggregates. `cohorts.py` defines what runs.

## The receipt

```json
{
 "schema": "garnet.sandbox-receipt/0.1",
 "capture": {
  "recorder": "linux-audit", "ruleset": "full", "kernel": "7.2.9",
  "rules": ["-a always,exit -F arch=b64 -S connect -F key=garnet", "..."],
  "kernel_counters_at_stop": {"enabled": "1", "lost": "0", "backlog_limit": "65536"},
  "declared_complete": true, "incomplete_reasons": [],
  "scope": "every connect/execve/clone/exit/open-for-write/unlink/rename syscall in this VM since arming; ...",
  "out_of_scope": ["reads", "sockets inherited from before arming", "raw/packet sockets", "kernel-internal traffic"]
 },
 "processes": {"executed": 23, "lineage": [{"comm": "node", "argv": ["node", "install.js"], "chain": "bash > node > sh > node"}]},
 "network": {
  "outbound_destinations": [
   {"destination": "storage.googleapis.com", "port": 443, "named_by_dns": true,
    "addresses": ["142.250.1.207"], "attempts": 2, "initiated": 2,
    "chains": [{"chain": "bash > node > sh > node", "connections": 2}]}
  ],
  "unnamed_destinations": [], "address_probes": 24
 },
 "files": {"paths_touched": 1056, "by_top_level": [{"prefix": "/work/node_modules", "paths": 1040}], "sample": ["..."]}
}
```

`declared_complete` is false whenever the kernel reports `lost > 0`, audit is not enabled
at stop, or any rule failed to load; the reasons are listed. Such a receipt is still
returned and is excluded from the cohort comparison.

## Cost

`ENGINEERING.md` has the measured numbers. Short version: sandbox create and first exec
unchanged (0.08 s / 0.9 s); arm 0.3 s + receipt 0.4 s per sandbox; connect/execve/clone
rules cost <10 %; the open-for-write rule costs ~25 µs per audited call (+8 to +40 % on
install-heavy steps, 10× on a pure create loop) and can be switched off with
`GARNET_RULES=nofiles`, which the receipt then declares. `lost 0` in every recorded
sandbox so far.

## Why kernel audit, and what would make this better

The VM guest kernel (7.2.9) ships `CONFIG_AUDIT`/`CONFIG_AUDITSYSCALL` but not
`CONFIG_FTRACE`, `CONFIG_KPROBES`, or BTF, so eBPF tracing recorders cannot attach inside
the guest today. Audit is the kernel-side, syscall-complete source that is available, with
built-in loss accounting, which is why coverage can be declared rather than assumed.
`kernel/README.md` lists what was observed and the opt-in kernel options that would let the
full Garnet recorder run in the same image.

## Next: allowlists from receipts

Modal Sandboxes take `outbound_cidr_allowlist` / `outbound_domain_allowlist`. The union of
destinations across the declared-complete receipts is exactly the list to put there. Not
wired in this script yet; the receipts already contain it.
