# The engineering case, measured (Modal VM Sandboxes, 2026-10-16)

Everything below was measured on Modal `runtime="vm"` sandboxes, kernel 7.2.9, 2 CPU /
2 GB, with the recorder in this repository. Unrecorded = same image, same workload,
recorder never armed. Medians over 10 sandboxes per cell unless stated.

## 1. Start-up: nothing

| phase | recorded | unrecorded |
|---|---|---|
| `Sandbox.create()` | 0.08 s | 0.08 s |
| first `exec` round-trip | 0.89 s | 0.90 s |
| arm recorder (auditd + 6 rules + DNS forwarder) | 0.32 s | - |
| write receipt | 0.44 s | - |

(100 + 100 sandboxes, `samples/SUMMARY.md`.) The image is the same; nothing runs until
armed. The two added phases together are ~0.75 s and are off the sandbox's cold path.

## 2. Runtime: where the cost is, and the knob

Kernel audit charges per matching syscall, and the userspace daemon writes every record.
Micro-benchmarks isolate each rule's hot path; `repo` is a realistic agent step
(`git clone` + `npm install` of expressjs/express).

| workload | recorded, full rules | recorded, `nofiles` | unrecorded |
|---|---|---|---|
| 200k `open(O_CREAT)` + unlink | 5.5 s | 0.57 s | 0.50 s |
| 5k fork+exec | 2.93 s | - | 2.71 s |
| 2k TCP `connect()` | 0.24 s | - | 0.26 s |
| clone + `npm install express` | 7.31 s (p95 10.3) | 7.37 s (p95 12.5) | 6.78 s (p95 9.5) |

Reading:
- connect/execve/clone cost is in the noise (<10 %). Process lineage and network
  attribution are effectively free.
- The open-for-write rule costs ~25 µs per audited call. A pure create-loop is 10× slower;
  a real install step is +8 % at the median with p95 variance that swamps it. (An earlier
  40-sandbox run put the same step at +37 %; run-to-run variance on this cell is large, so
  treat the file-rule cost as "between +8 % and +40 % on install-heavy steps" until measured
  at larger n.)
- `GARNET_RULES=nofiles` removes the file rules: the receipt then declares `file writes`
  out of scope. The tradeoff is explicit in the receipt, not hidden.
- Memory: `auditd` RSS ≈ 2.2 MB, DNS forwarder ≈ 15 MB. Audit log per run: 150 KB to 3.7 MB.
- Loss accounting: `lost 0` in all 320 recorded sandboxes today at `backlog_limit 65536`.
  If the kernel ever drops records, the receipt says so and is excluded from the cohort.

## 3. Concurrency: 100 at once

200 sandboxes in 44 s wall through one `.map()`; 100 recorded in parallel, every receipt
complete. Arming p95 0.73 s under that fan-out.

## 4. What this is not

- It is not better capture than Modal has host-side. In gVisor, the sentry sees every
  syscall; Modal's own tooling is the right place for platform-wide visibility. Kernel audit
  inside a VM is stock Linux and anyone can run it.
- It is not eBPF. The guest kernel has no FTRACE/KPROBES/BTF, so the full Garnet recorder
  (Jibril) cannot attach; `kernel/README.md` lists the opt-in options that would change that.
- Receipts are per-syscall attribution, not packet capture: a connection's destination is
  the address the process asked for, named by the DNS answer the sandbox itself received.

## 5. Where the value actually is

The customer-facing artifact. Modal sees everything and the customer gets nothing per run.
A receipt per sandbox, with coverage declared and the union of destinations as the proposed
`outbound_domain_allowlist`, is a product gap on the customer's side, not a capability gap on
Modal's. On VM Sandboxes specifically there is no sentry in the guest, so a guest-side
receipt is the only per-process record that exists today.

## 6. What a 100-sandbox cohort found without being told what to look for

Dependency installs, 60 npm + 40 PyPI top packages, one per sandbox, nothing constructed:
94 contacted only their registry. 6 contacted something else, every one via
`bash > node > sh > node` (a postinstall script): puppeteer → storage.googleapis.com,
cypress → cdn.cypress.io, sqlite3 and canvas → github.com + release-assets.githubusercontent.com,
node-sass → github.com + nodejs.org, serverless → install.serverless.com. None of these is
wrong; all of them are what a customer needs in the allowlist and did not know.

SWE-bench Lite rollouts (official `swebench/sweb.eval.*` images pulled straight into VM
Sandboxes, gold patch applied, FAIL_TO_PASS run): 0 hosts contacted, writes confined to
`/testbed` and the conda env. That is the per-rollout statement an RL grader wants, with the
kernel's own loss counter behind it.
