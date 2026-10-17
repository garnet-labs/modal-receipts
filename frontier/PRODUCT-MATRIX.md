# What the frontier matrix means for the product

FACTS.md is kernel-flag × Jibril-program. This page is the same evidence re-cut by how a customer
integrates (rows) and what Garnet capability they get there (columns). Every cell cites a measured run
from this repo, the GitHub product, or the sibling lanes (samples/, e2b/, FACTS.md). Nothing here is
projected.

## Legend

- **full** — Jibril-grade or equivalent, with the chain.
- **partial** — the capability exists but with a named gap.
- **no** — not today; the unlock is named in the last column.
- Sensor columns (1–5) are *capture*: commodity wherever the platform can see the same thing itself.
- Garnet columns (6–10) are the *product layer*: identical across rows, independent of the sensor.

## The matrix

| Integration path (how the customer runs agents) | 1 Process lineage (root → action) | 2 Egress → process | 3 Destination names | 4 Files per process | 5 Exec detail (argv) | 6 Record outside the agent's reach | 7 Declared coverage + loss | 8 Evidence → policy, enforced by the substrate | 9 Run-vs-run / cohort comparison | 10 Reviewer / grader / MCP consumption | Overhead (measured) | Real agent run shown | Sensor | What unlocks the "no" cells |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **GitHub Actions** (garnet-org/action; production) | full | full | full (DNS→process) | full | full | partial — sensor is a root service beside a `runner`-user job; job has sudo on hosted runners | **no** — public profile has no `capture{declared_complete, lost}` block (ENG-1615/ENG-1400) | partial — managed netpolicy, enforce mode real on v2.3.0; **not applied on `pull_request` runs** | full (Runtime Review: changed / unchanged / undeterminable) | full (App comment, hosted MCP; CodeRabbit cited it on pnpm #108) | not measured in these lanes | yes — ABI runs (Claude), Devin, gh-aw | Jibril | capture block in the profile; netpolicy on PR runs (control-plane) |
| **Self-hosted E2B Embed / Devin Outposts on an operator kernel** (6.18 + `MODULES BPF_JIT FTRACE_SYSCALLS KPROBES`) | full (72/76 programs; `systemd > envd > devin > devin-remote > bash > node`) | full | full | full (1,820 paths in the E2B lane) | full | partial — in-guest sensor as root; agent also root/sudo; a kill shows as a missing profile, not yet declared | partial — Jibril reports programs attached/failed; not surfaced in the profile | **not tested** — Jibril netpolicy is available in-guest, no enforcement run yet | full (same profile schema as GitHub) | partial — same schema, so the same MCP tools apply; not exercised on these profiles | Jibril ready in 3 s, 112 MB RSS; workload overhead not measured | yes — real Devin Outpost session, n=1 (samples/outpost-e2b) | Jibril | 2.4 GB rootfs → bigger template for cohorts; a netpolicy enforce run |
| **Modal VM Sandbox** (Sidecar relay + in-VM audit) | partial — ppid chain from audit `execve`/`connect` (`bash > node > sh > node`); no fork/exit timing | full for TCP/443 (SNI ↔ pid via audit) | full for 443 (SNI); non-443 declared out of coverage | **no** | full (audit argv) | **full — Sidecar is outside the guest; root edit of the in-VM log flips the verdict** | full (`capture{...}`, lost=0 on n=30 and the Outpost run) | **full — receipt union → `outbound_domain_allowlist`; Modal enforced 10/10, refused the out-of-list host and the refusal is recorded** | full (n=30 cohort: 30/30 agree, 6 natural postinstall fetchers) | partial — receipt JSON + HTML; not yet pushed to the App/MCP | Sidecar up 0.74 s p50; +1 ms/connection; in-VM arm 0.35 s | yes — real Devin Outpost session (samples/outpost); no Claude/Codex (no key) | audit + Sidecar | files/lineage detail: Modal ships the 9 Kconfig lines (→ Jibril row) or Jibril degraded mode (ENG-1629) |
| **Vercel Sandbox** (ptrace, or cgroup-BPF + fanotify) | ptrace: full (139 pids, 30 execs) · cgroup+fanotify: partial (exec/open paths, no fork/exit — child pid ns silences cn_proc) | ptrace: full · cgroup: destination + pid/comm | partial — IPs + DNS queries; Vercel sees domains host-side | ptrace: full (19,630 writes) · fanotify: open/exec paths | ptrace: full | **no** — recorder is in-guest, agent has sudo | full (receipt shape, lost=0) | partial — Vercel enforces a DNS allowlist host-side (10 ms refusal); not yet derived from a receipt | full (same receipt shape) | no | ptrace +31–37% · cgroup+fanotify +2–8% (single sample) | no — scripted workload only (AI Gateway 402) | ptrace / cgroup-BPF | `CONFIG_DEBUG_INFO_BTF`+`BPF_EVENTS`+`AUDIT` from Vercel (→ Jibril row); ENG-1629 for the cgroup path; an LLM key for a real session |
| **Hosted E2B** (stock 6.1 kernel; audit recorder) | partial (audit ppid chain) | partial (IP + pid; no SNI relay) | partial (IPs only) | no | full (audit argv) | no | full (lost=0, n=10) | not tested | full | no | arm 0.25 s, receipt 0.08 s, e2e 5.9 s | no | audit | E2B `fc-kernels`: `MODULES`+`BPF_JIT` (+2 lines) → Jibril 72/76 as in the Embed row |
| gVisor / container runtimes (Modal default, others) | no — host-blind from the guest | no | no | no | no | n/a | n/a | n/a | n/a | n/a | — | — | none | platform-side logs only; not a Garnet row today |

## Read it as core value vs. integration

**Core value (columns 6–10) is the same product on every row.** Receipt contract with declared coverage,
tamper-independence where the substrate allows a second observer, cohort comparison, evidence-derived
policy that the *platform* enforces, and consumption by reviewers/graders/MCP. Only the Modal row has
all five today; GitHub has 9–10 and misses 7; the rest have 7 and 9 and miss 8 and 10. That gap list
is the product backlog, not a kernel problem:

| Gap | Row(s) | Owner | Tracker |
|---|---|---|---|
| `capture{declared_complete, lost}` in the public profile | GitHub | control-plane | ENG-1615 / ENG-1400 |
| Managed netpolicy on `pull_request` runs | GitHub | control-plane / action | (loop-demo lane fact) |
| Push sandbox receipts into the App/MCP so column 10 is one path | Modal, Vercel, E2B | garnet-labs | not filed |
| Jibril degraded mode: non-fatal loading, declared per-feature coverage, cgroup fallback, procfs source, `btf_custom_path` | Modal, Vercel, hosted E2B | Jibril | ENG-1629 |

**Capture (columns 1–5) is Jibril-grade exactly where someone we trust owns the kernel** (GitHub runners,
self-hosted E2B, Outposts on an operator image). On hosted microVMs it is whatever Linux gives us without
BTF/tracepoints: audit (Modal, E2B), ptrace or cgroup-BPF + fanotify (Vercel). Those are commodity and
we say so; the platform's host-side view is usually at least as good for destinations. The ask that moves
a hosted row into the Jibril column is a fixed Kconfig list per vendor (FACTS.md §E), and the ask that
makes Jibril honest meanwhile is ENG-1629.

## What we can say per row, and what we cannot

- **GitHub:** "Every CI job of your agent gets a Jibril-grade record and a reviewer-readable verdict." Cannot say: "the record declares its own completeness" (yet) or "policy applies to fork PRs".
- **Self-hosted E2B / Outposts:** "Bring your own kernel with four config lines and every sandbox session gets the same Jibril record as CI." Cannot say: anything about cohorts (n=1, rootfs limit) or enforcement.
- **Modal:** "Every sandbox run gets a receipt the agent cannot edit, and the receipt writes the allowlist Modal enforces." Cannot say: "Jibril-grade" or "files".
- **Vercel:** "A receipt with chains and files exists from a Firecracker VM we don't own, today." Cannot say: "tamper-independent", "low overhead" (ptrace), or "a real Claude/Codex session".
- **Hosted E2B:** "Receipts work on stock E2B; Jibril needs two kernel lines from E2B." Cannot say: names, files, or enforcement.
- **gVisor:** nothing. Host-side only.
