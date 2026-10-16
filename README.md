# Every sandbox run gets a receipt

A `modal run` script. It launches Modal **VM Sandboxes** (`runtime="vm"`) from one
image, runs a real coding task on a real open-source repository inside each one,
fans out with `.map()`, and returns one **execution receipt per run**:

- process lineage (every `execve`, with argv, as root-to-action chains),
- every outbound connection, attributed to the process chain that made it, named
  by the sandbox's own DNS answers,
- files created / written / removed,
- **coverage declared by the kernel**, not by us: the audit subsystem's own
  `enabled` / `lost` / `backlog_limit` counters and the exact rule set, so each
  receipt says whether it saw everything in scope.

Then it tells you which runs contacted the same hosts and which contacted something
new, and what the recorder cost in cold-start and runtime, measured on the same
cohort with and without it.

Nothing leaves your account. Receipts come back to your terminal and `./out/`.

## Run it

```sh
pip install modal && modal setup          # once
git clone <this repo> && cd <this repo>
modal run receipts.py --runs 10 --baseline 10     # ~2 minutes, 20 VM sandboxes
modal run receipts.py                              # 100 recorded + 100 unrecorded
```

Flags: `--runs N` recorded sandboxes, `--baseline N` unrecorded sandboxes (cost
comparison), `--constructed K` runs that include one labelled extra fetch
(default 3; see below), `--repo URL` any Python repository with `tests/`,
`--out DIR`.

## What is in the image

Only Modal primitives and stock Ubuntu packages:

```
ubuntu:24.04 + git curl auditd python3   +   guest/   (three small files)
```

- `guest/recorder.sh` arms the Linux kernel audit subsystem (`auditctl` rules on
  `connect`, `execve`, `clone`, `exit_group`, open-for-write, `unlink`/`rename`)
  and starts a 90-line DNS forwarder on `127.0.0.1:53` that logs the answers the
  sandbox's resolver returns.
- `guest/workload.sh` is the task: clone → venv → `pip install -e . pytest` →
  pytest → edit a file → commit → pytest. Key-free, real network.
- `guest/receipt.py` reads `/var/log/audit/audit.log` and the DNS log and writes
  the receipt. It infers nothing: a chain is the recorded parent path of the
  process that called `connect()`.

The driver, `receipts.py`, is one Modal function (`run_one`) that creates a VM
Sandbox, arms, runs, stops, collects, terminates; the local entrypoint calls
`run_one.map(specs)` and aggregates.

## The receipt

```json
{
 "schema": "garnet.sandbox-receipt/0.1",
 "capture": {
  "recorder": "linux-audit",
  "kernel": "7.2.9",
  "rules": ["-a always,exit -F arch=b64 -S connect -F key=garnet", "..."],
  "kernel_counters_at_stop": {"enabled": "1", "lost": "0", "backlog_limit": "65536"},
  "declared_complete": true,
  "incomplete_reasons": [],
  "scope": "every connect/execve/clone/exit/open-for-write/unlink/rename syscall in this VM since arming; ...",
  "out_of_scope": ["reads", "sockets inherited from before arming", "raw/packet sockets", "kernel-internal traffic"]
 },
 "workload": {"origin": "https://github.com/pallets/click", "head": "<sha the task ran on>", "head_after_edit": "<sha>"},
 "processes": {"executed": 51, "lineage": [{"pid": 1234, "comm": "git", "argv": ["git", "clone", "..."], "chain": "bash > git"}]},
 "network": {
  "outbound_destinations": [
   {"destination": "files.pythonhosted.org", "port": 443, "named_by_dns": true,
    "addresses": ["151.101.0.223", "..."], "attempts": 54, "initiated": 54,
    "chains": [{"chain": "bash > pip > python3", "connections": 27}]}
  ],
  "unnamed_destinations": []
 },
 "files": {"paths_touched": 3729, "by_top_level": [{"prefix": "/work/repo", "paths": 3700}], "sample": ["..."]}
}
```

`declared_complete` is false whenever the kernel reports `lost > 0`, audit is not
enabled at stop, or any rule failed to load; the reasons are listed. A receipt
that is not declared complete is still returned, and is excluded from the cohort
comparison.

## The cohort summary

`out/SUMMARY.md`, printed at the end. Shape:

```
## 97 runs contacted the same 4 hosts. 3 contacted something new.
- `files.pythonhosted.org:443`  - `github.com:443`  - `pypi.org:443`  - ...
- run 000 (constructed): `httpbin.org:443` via `bash > python3`
```

**Constructed cases are labelled.** `--constructed 3` makes three runs execute
one extra, clearly marked step in `workload.sh` (a Python one-liner fetching
`https://httpbin.org/get`, standing in for a dependency's setup hook). The runs
are named `run-NNN-constructed.json` and the summary says `(constructed)`. The
other 97 are the real task, unchanged; full attribution on a run that contacted
nothing new is the normal, useful result.

## Cost

Measured on the same cohort, recorded vs unrecorded. Our 100 + 100 run on
2026-10-16 (`samples/SUMMARY.md`; 200 VM sandboxes, 44 s wall for the whole cohort,
100/100 receipts declared complete):

| phase | recorded (median / p95) | unrecorded (median / p95) |
|---|---|---|
| sandbox create | 0.08 / 0.35 s | 0.08 / 0.25 s |
| first exec | 0.89 / 1.37 s | 0.90 / 1.18 s |
| arm recorder | 0.32 / 0.61 s | - |
| workload | 6.47 / 7.90 s | 6.44 / 8.49 s |
| build receipt | 0.44 / 1.17 s | - |
| total | 8.41 / 10.45 s | 7.71 / 9.60 s |

What each phase times:

| phase | what is timed |
|---|---|
| sandbox create | `Sandbox.create()` returning |
| first exec | first `sb.exec("true")` round-trip |
| arm recorder | `auditd` + rules + DNS forwarder up |
| workload | the task, end to end |
| build receipt | parse audit log, write JSON |

The recorder adds nothing to sandbox creation (same image, nothing runs until
armed). Arming and receipt generation are the two added phases, about 0.75 s
together at the median; the workload itself ran in the same time with and
without the kernel audit rules on this task (the difference is inside run-to-run
noise). Your numbers will differ; the script prints them.

## Why kernel audit, and what would make this better

Modal's VM guest kernel (7.2.9) ships `CONFIG_AUDIT`/`CONFIG_AUDITSYSCALL` but not
`CONFIG_FTRACE`, `CONFIG_KPROBES`, or BTF, so eBPF tracing recorders cannot attach
inside the guest today. Audit is the kernel-side, syscall-complete source that is
available, with built-in loss accounting, which is why coverage can be declared
rather than assumed. `kernel/README.md` lists what was observed and the opt-in
kernel options that would let the full Garnet recorder run in the same image.

## Next: allowlists from receipts

Modal Sandboxes take `outbound_cidr_allowlist` / `outbound_domain_allowlist`. The
union of destinations across the declared-complete, non-constructed receipts is
exactly the list to put there. Not wired in this script yet; the receipts already
contain it (`network.outbound_destinations[].destination` and `.addresses`).
