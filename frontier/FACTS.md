# Jibril frontier: capture inside hosted sandbox guests without a vendor kernel change

Product reading of this evidence (integration path × capability, what we can and cannot say): [PRODUCT-MATRIX.md](PRODUCT-MATRIX.md).

Lane: make Jibril-grade capture work inside Modal VM Sandbox, Vercel Sandbox and E2B hosted guests.
All runs 2026-10-17 00:44-00:59 UTC. Jibril under test: `jibril-releases` v2.17.0 (`rel/jibril`, 91,389,176 bytes, sha256 in `out/a1-20261017T004710Z/out/jibril.sha256`).
Probe code: `frontier/guest/*`, driver `frontier/probe_a1.py`. Raw logs: `frontier/out/<run>/out/*` (see index at the end). Nothing was run on the Devin VM except the Modal/Vercel drivers.

The metric is "attached N/76": 76 is the number of programs Jibril's loader instantiates (`new prog` lines in its own log). The release ELF objects contain 122 programs = 75 entry programs + 47 `tail_*` tail-call programs; the per-program loader probe below reports against 122.

## Substrate x result

| | Modal VM Sandbox | Vercel Sandbox | E2B hosted |
|---|---|---|---|
| Kernel | 7.2.9, cloud-hypervisor, root | 6.18.49, Firecracker, uid 1000 + sudo | LTS 6.1 (6.1.158 config), Firecracker |
| `/sys/kernel/btf`, tracefs, `/boot`, `/lib/modules` | all absent | all absent | BTF + tracefs present (prior lane) |
| BPF types accepted (14 probed) | 5: cgroup_skb, cgroup/connect4, cgroup/sock_create, cgroup/sendmsg4, sockops | same 5 | n/a this lane |
| Jibril v2.17.0, per-program isolated load+attach | 12/122 (all cgroup_skb) | 12/122 (identical) | 4/76 stock, 52/76 or 72/76 with operator kernel (prior lane) |
| Jibril v2.17.0 real run | 76 programs, 37 attach failures, 5 object load failures, exit 1 | identical counts | not rerun |
| + foreign BTF via `btf_custom_path` (constructed) | 26/122 | not run (same expected) | n/a |
| cgroup-BPF recorder (no BTF) | 5/5 attached; 19/19 destinations = audit; tgid match 19/19; overhead ~0% | 5/5 attached; overhead +2..8% (ptrace baseline was +31-37%) | n/a |
| proc connector / fanotify | not tested (audit already works there) | cn_proc silent (child pid ns); fanotify works with exec paths | n/a |
| Custom kernel path | none (kexec dead end, prior lane) | none | none: kernel fixed per template at build time |

## A. Modal, no kernel change

### A1. Which program types and which Jibril programs can load at all

Hypothesis: without FTRACE/KPROBES/BPF_EVENTS/DEBUG_INFO_BTF only the cgroup and socket program families can load; every tracing family fails at load, not at attach.

Run: `probe.sh` in a `runtime="vm"` sandbox (image ubuntu:24.04 + clang 18 + libbpf 1.3), 00:47:08-00:47:25 UTC, Modal app `ap-k5C5DmXoMX3EBUomjORkbr`.
1. `types.bpf.c`: one minimal program per type, loaded alone and attached (`attach_probe.c`). Output `type-probe.jsonl`.
2. Jibril's embedded objects carved out of the release binary (`carve.py`, 22 ELF objects, 122 programs), each program loaded alone with every other program's autoload off, then attached. Output `jibril-progs.jsonl`.
3. `bpftool feature probe kernel` (`bpftool-feature.txt`), `/proc/config.gz` excerpt (`kconfig.txt`), filesystem surfaces (`kernel-surfaces.txt`).

Numbers (Modal 7.2.9):
- Type probe, 14 types: attach OK = `cgroup_skb/egress`, `cgroup/connect4`, `cgroup/sock_create`, `cgroup/sendmsg4`, `sockops`. Load `-EINVAL` (program type unknown to the kernel; no `CONFIG_BPF_EVENTS`) = `tracepoint`, `raw_tracepoint`, `kprobe`, `perf_event`, `uprobe`. Load `-ESRCH`/`-ENOENT` "failed to find valid kernel BTF" = `fentry`, `tp_btf`, `iter/task`, `lsm`.
- Jibril programs by section on this kernel: cgroup_skb 12 OK / 22 "no vmlinux BTF" (CO-RE relocations) / 4 EINVAL; fentry 0/12, fexit 0/17, tp_btf 0/6, iter 0/12 (all "no vmlinux BTF"); tracepoint 0/29 (20 BTF, 9 EINVAL); kprobe/kretprobe 0/6; uprobe 0/2.
- Kconfig: `CONFIG_BPF_SYSCALL=y CONFIG_BPF_JIT=y CONFIG_CGROUP_BPF=y CONFIG_NET_CLS_BPF=y CONFIG_NETFILTER_BPF_LINK=y CONFIG_PERF_EVENTS=y CONFIG_KALLSYMS=y CONFIG_AUDITSYSCALL=y CONFIG_PROC_EVENTS=y CONFIG_FANOTIFY=y CONFIG_SECURITY_NETWORK=y CONFIG_LSM="landlock,lockdown,yama,loadpin,safesetid,ipe,bpf"`; not set: `CONFIG_BPF_LSM`, `CONFIG_BPF_EVENTS`, `CONFIG_DEBUG_INFO_BTF`, `CONFIG_FTRACE`, `CONFIG_KPROBES`, `CONFIG_UPROBES`, `CONFIG_MODULES`. `/proc/kallsyms` has 117,614 symbols including `security_socket_connect`, so the hook functions exist; only the attachment machinery is missing.
- Real Jibril run (`--config` derived from `etc/config/standalone.yaml`, log level debug; `jibril-run.clean.log`): `kernel version: 7.2.9`, `ksymbols` warns `available_events`/`available_filter_functions` missing, then "symbol can't be checked, trying program anyway" for every gated program; 76 `new prog`; libbpf: "kernel BTF is missing at '/sys/kernel/btf/vmlinux'", "failed to determine tracepoint 'syscalls/sys_enter_execve' perf event ID: -ENOENT", "map 'jb_l4jmpsin': can't use BPF map without FD"; 37 "failed to attach", 5 "failed to load object" (`tasks`, `files`, ...), `Run summary: fatal errors were found, execution failed`, exit 1.

Verdict: confirmed. On 7.2.9 Jibril's only loadable family is `cgroup_skb` (its network flow programs); 12 of its 38 cgroup_skb programs load today, the other 22 only fail because they contain CO-RE relocations and there is no BTF to resolve them against. Everything exec/file/process related (fentry/fexit/tp_btf/iter/tracepoint/kprobe) cannot load on this kernel under any userspace change.

### A1b. Can BTF be supplied from outside the guest

Hypothesis: libbpf's `btf_custom_path` can replace `/sys/kernel/btf/vmlinux` for CO-RE, but not for program types whose attach needs in-kernel BTF.

Facts: no kernel image, `System.map`, `/boot` entry or `/lib/modules` is visible in the guest (`kernel-surfaces.txt`), so BTF for 7.2.9 cannot be generated from inside; it would have to be published by Modal (pahole over their vmlinux). Jibril's loader opens objects with only `pin_root_path` set (`pkg/singleton/ebpf/ebpf.c`, `bpf_object_open_opts`), so it has no way to consume an external BTF today.

Constructed run (labelled, not a valid 7.2.9 BTF): the Devin VM's 6.8 `vmlinux` BTF (6,152,164 bytes) shipped into the guest and passed as `btf_custom_path` (`btf_probe.sh`, 00:58:29 UTC, app `ap-AD6FMc40SgNY7aGR90oMvW`, `jibril-progs-custombtf.jsonl`). Result: 26/122 load+attach (was 12); the 14 new ones are all cgroup_skb (`obj17` dns53 tails, `obj20` `jb_cgroup_skb_ingress/egress` + l3/l4 tails). fentry/fexit/tp_btf/iter still fail (the kernel itself has no `btf_vmlinux` to resolve `attach_btf_id`), tracepoint/kprobe/uprobe still EINVAL. 10 cgroup_skb programs still fail with EINVAL/EACCES against the wrong-kernel BTF.

Verdict: external BTF is worth at most the remaining cgroup_skb programs; it needs both a Modal-published BTF and a Jibril option to load it. It does not unlock any tracing program.

### A2. What a cgroup-BPF-only recorder captures versus audit

Hypothesis: `cgroup/connect4|6`, `cgroup/sendmsg4|6`, `cgroup/sock_create` attached at the cgroup root give every outbound destination with pid/tgid/comm, with no BTF and negligible overhead.

Run: `cgrec.bpf.c` + `cgrec.c` (no CO-RE, ring buffer, helpers `bpf_get_current_pid_tgid`/`bpf_get_current_comm`), auditd with `-S connect -S execve` running in parallel; workload = 3 curls (example.com, pypi.org, ipv6.google.com), python urllib to github.com, a raw UDP DNS query to 8.8.8.8, `getent hosts modal.com`; then 300 local curls with and without the recorder. Output `cgrec.jsonl`, `audit.log`, `compare.json`, `overhead.txt`.

Numbers (Modal): 5/5 programs attached. 853 events: 423 sock_create, 429 connect, 1 sendmsg. Distinct (addr,port) destinations: recorder 19, audit 19, `only_in_cgroup = []`, `only_in_audit = []`. pid attribution: for all 19 destinations the set of recorder `tgid`s intersects the set of audit `pid`s (`tgid_attrib_matches: 19`). The recorder's `pid` field is the thread id (curl's resolver thread differs from the audit pid), so `tgid` is the field to match on; the first version of `compare.py` compared last-seen pids and reported 18/19, the committed version compares tgid sets and `compare.json` was regenerated from the committed raw files. comm values: curl, python3, getent. Overhead: 1,312 ms (recorder on) vs 1,319 ms (off) for 300 connections, i.e. none measurable. The first attempt failed in the verifier ("invalid bpf_context access off=8": reading `user_ip6` inside a connect4 program); fixed by separate v4/v6 paths, kept in `out/a1-20261017T004428Z` as the failed run.

Verdict: confirmed. Per-connection destination + pid/tgid/comm is available on 7.2.9 from cgroup hooks alone; it is strictly a subset of what Jibril's `cgroup_skb` flow programs plus its process tree deliver (no argv, no file access, no parent chain), but it is kernel-side and complete for destinations.

### A3. Could a Jibril degraded mode exist on this kernel, program by program

Today: 0 attached, exit 1, because (a) `problems.P.ErrFatal` is called on object load failure and on every attach failure (`pkg/singleton/ebpf/lifecycle-register.go`), (b) the per-program gate in `prog.go` (`symbolAvailable`) falls through to "try anyway" when tracefs is absent, so nothing is skipped up front, (c) the network object's own tail-call maps cannot be populated once sibling programs fail.

What would attach on 7.2.9 if failures were non-fatal and CO-RE had BTF: 26 of 38 cgroup_skb programs (flows, l3/l4/l7 dns tails, netpolicy tails), which carry the network flow feature end to end, provided the process attribution they look up from the task maps is replaced (those maps are filled by the fentry/iter programs that cannot load).

| Jibril program family | On 7.2.9 | Needed Jibril change |
|---|---|---|
| `cgroup_skb/ingress|egress` + tails (38) | 12 load; 26 with external BTF | load `btf_custom_path` from config/env; keep going when a sibling object fails; declare `flows` coverage only |
| `fentry/fexit` (29: socket, file, mknod, rename, truncate, write, fsync, hrtimer) | never (no btf_vmlinux, no fentry trampolines) | mark optional per hook; declare `files`, `sockets` as uncovered; for sockets add `cgroup/connect*`, `sendmsg*`, `sock_create` programs as the fallback source of (pid, dst) |
| `tp_btf/sched_process_{exec,exit,fork}` (6), `raw_tracepoint` (2), `tracepoint/syscalls/*` (29) | never (no tracepoints, no BPF_EVENTS) | process lifecycle fallback: proc connector (`CONFIG_PROC_EVENTS=y` here; needs init pid ns) + `/proc` scrape for argv/env; declare `exec`/argv as "userspace-sourced" |
| `iter/task`, `iter/task_file` (12) | never (needs BTF) | replace startup enumeration with a `/proc` walk |
| `kprobe/kretprobe` (6), `uprobe` (2) | never (no KPROBES/UPROBES) | optional; declared uncovered |

Verdict: a degraded mode is possible and would be honest about its coverage: flows + destinations with pid/comm (kernel-side via cgroup hooks), process tree from proc connector/procfs (userspace, racy for short-lived processes), no file access, no argv from the kernel. It is a loader-policy change plus one new small cgroup object; it is not a port of the existing programs.

## B. Jibril degradation proposal (document, not a PR)

Hypothesis: per-program degrade + declared coverage can be added without touching the eBPF programs, except `jb_iter_init_02` for 6.1.

Proposed shape (evidence: `lifecycle-register.go`, `prog.go`, `ebpf.c`, the attach logs above):
1. Capability probe before load: `bpftool`-style probes for each section type the objects contain (the 14-type probe above takes 1 s); programs of unsupported types are set `autoload=false` instead of tried and failed.
2. Load/attach failures become per-program results (`AttachFailure` already exists in `Metrics`); `ErrFatal` only if a program listed as required for an enabled feature is missing.
3. Tail maps and `cgroup_skb` entry programs are populated from whichever tails loaded; features declare their required program set, and the agent emits a `coverage` block (per feature: full / degraded(source) / none) in its startup log and in the profile it submits.
4. `btf_custom_path` from config, documented as "vendor-published BTF".
5. The 6.1 verifier issue: `jb_iter_init_02` (`ebpf/files.bpf.c`) inlines both `update_maps_from_file` (dentry walk, `#pragma unroll` over `_max_dentry_ = 10`, twice: walk + reverse assemble) and `update_maps_from_pathname` (`#pragma unroll` over `_max_unix_sock_ = 108`) in one program; on 6.1 (no open-coded iterators, weaker state pruning) the unrolled 108-iteration loop plus two 10-deep walks exceeds the processed-instruction budget. Fix options, smallest first: (a) move the unix-socket branch into a second `iter/task_file` program (`jb_iter_init_02b`) so each program carries one unrolled loop; (b) replace the 108-wide unroll with a bounded `bpf_probe_read_kernel_str` + `bpf_loop` (5.17+) or a `__noinline` subprogram so the verifier checks it once; (c) lower `_max_unix_sock_` for the iterator path only. Also make the `files` object non-fatal so one program's rejection does not drop the 51 others (the prior lane saw 52/76 instead of 72/76 for exactly this reason).

Patched build before/after on an E2B 6.1 guest: not run in this lane. Reason: no Go/clang toolchain or 6.1 guest exists on this VM, the E2B Embed stack is owned by the sibling lane (session 19ea70d5, Outpost on Modal + E2B 6.18 variant), and building `garnet-org/jibril` inside a third-party sandbox was not authorised. The split in (a) is mechanical and testable there in one run; expected effect is 52/76 -> 72/76 on 6.1 with the operator kernel options, as measured for 6.18 by the prior lane.

Verdict: proposal ready; the 6.1 fix is a one-program split; counts after the fix are unverified until a 6.1 guest run.

## C. Vercel Sandbox

Hypothesis: with sudo, cgroup-BPF + proc connector + fanotify give per-process attribution without ptrace, at a fraction of the +31-37% ptrace cost.

Run: Vercel MCP `create_sandboxes_v4` (team garnet-labs, project `prj_pOl7Lk0UK7fQr2ZOPVKG75NmmJAp`, iad1, 2 vCPU/4 GB, universal image, session `sbx_0NNVWhuDKU4ax5DYz7rVTylBUXy8`), apt clang/libbpf/linux-tools, `vercel_probe.sh` 00:48:39-00:52:14 UTC and `vercel_probe2.sh` 00:55 UTC; artifacts `out/vercel-20261017T0048Z/{out,out2}`. Sandbox stopped afterwards (snapshot `snap_iisTgHkSrJuctLgIUEbz3fQpbDXS`).

Numbers (6.18.49, uid 0 via sudo, `CapEff 000001ffffffffff`):
- Same 5/14 types accepted, same Jibril 12/122 per-program result, same real-run outcome (76 `new prog`, 37 attach failures, 5 object failures, exit 1). bpftool 7.7.0 reports 61 helpers/features available.
- BTF path: `/boot` empty, no `/lib/modules`, no `/usr/src` kernel headers, cmdline `init=/opt/vercel/celld-init.sh build_version=2026.10.16-cb918b1a...`; nothing in the image can produce BTF for 6.18.49. `/proc/kallsyms` 98,099 symbols, `security_socket_connect` present.
- cgroup recorder: 5/5 attached, 1,236 events on the workload, destinations with pid/tgid/comm as on Modal.
- proc connector: netlink bind + `PROC_CN_MCAST_LISTEN` succeed but zero events. Cause: `sandbox-init` (PID 1) and every command run in pid namespace inode 4026532093, not the kernel's init pid namespace, and `cn_proc` only reports there. Not fixable from inside.
- fanotify: `FAN_MARK_FILESYSTEM` on `/` with `FAN_OPEN_EXEC|FAN_OPEN` works and resolves paths (`/usr/bin/curl` pid 5621, `/usr/bin/python3.14`, `/usr/lib/cargo/bin/coreutils/id`); the first run with `FAN_MODIFY` and no self-filter produced 1.47 M self-feedback events (recorder writing its own log), kept in `out/pcrec-summary.json` as the failed configuration.
- Overhead, 300 local HTTP requests: baseline 2,158 ms; cgroup recorder 2,334 ms (+8%); cgroup + fanotify/cn_proc 2,207 ms (+2%); fanotify/cn_proc only 2,213 ms (+2.5%). Single-sample timings, so these are within run-to-run noise; the ptrace recorder measured +31-37% in the prior lane.

Verdict: confirmed for destinations (cgroup-BPF) and exec/open paths (fanotify) with pid attribution at single-digit-percent cost; process lifecycle events need ptrace or `/proc` polling because the proc connector is blind in Vercel's pid namespace. No BTF path exists on this image.

## D. E2B hosted

Source: `https://docs.e2b.dev/template/how-it-works.md` section "Kernel" (fetched 00:40 UTC): "E2B sandboxes run on an LTS 6.1 Linux kernel", version "depends on when your template was built", "Kernel versions are fixed at template build time", "the kernel cannot be upgraded or changed for that template", configs at `github.com/e2b-dev/fc-kernels/tree/main/configs`. That repo (last commit 2026-08-10) has `6.1.102.config` and `6.1.158.config`; `6.1.158.config` has `# CONFIG_MODULES is not set` and `# CONFIG_FTRACE is not set`, matching the Embed stock kernel the prior lane measured (4/76). No SDK or template option selects a kernel; `docs.e2b.dev/billing.md` lists Hobby/Pro/Enterprise with no kernel dimension. No account was created.

Verdict: hosted E2B has no customer-side kernel path; the ask has to go to E2B (their `fc-kernels` build).

## E. Vendor asks, per platform

All three guests already have `CONFIG_BPF_SYSCALL`, `CONFIG_BPF_JIT`, `CONFIG_CGROUP_BPF`. The missing lines are the same family everywhere; the smallest test is the 14-type probe in this repo (`frontier/guest/types.bpf.c` + `attach_probe.c`, ~1 s) followed by `jibril` with the standalone config, success = `attached 72+/76`, exit 0.

Modal (kernel 7.2.9), evidence `out/a1-20261017T004710Z/out/kconfig.txt`:
```
CONFIG_DEBUG_INFO_BTF=y
CONFIG_FTRACE=y
CONFIG_FUNCTION_TRACER=y
CONFIG_DYNAMIC_FTRACE=y
CONFIG_FTRACE_SYSCALLS=y
CONFIG_KPROBES=y
CONFIG_UPROBES=y
CONFIG_BPF_EVENTS=y
CONFIG_TRACEPOINTS=y
```
plus mounting `tracefs` at `/sys/kernel/tracing` in the guest init. Smallest test: `ls /sys/kernel/btf/vmlinux /sys/kernel/tracing/available_filter_functions` then `attach_probe types.bpf.o` expecting 14/14.

Vercel (kernel 6.18.49), evidence `out/vercel-20261017T0048Z/out/kernel-surfaces.txt`, `bpftool-feature.txt`: the same nine lines, plus `CONFIG_AUDIT=y CONFIG_AUDITSYSCALL=y` (audit netlink is absent today), plus running `sandbox-init` in the init pid namespace or exposing `cn_proc` there if proc connector is wanted. Smallest test: as above, plus `auditctl -s`.

E2B hosted (6.1.158 config), evidence `fc-kernels/configs/6.1.158.config` and the prior lane's 6.18 result: `CONFIG_MODULES=y` (prerequisite for `CONFIG_BPF_JIT` taking effect on 6.1 and for fentry trampolines), `CONFIG_FTRACE=y CONFIG_FUNCTION_TRACER=y CONFIG_DYNAMIC_FTRACE=y CONFIG_FTRACE_SYSCALLS=y CONFIG_KPROBES=y`, and preferably a 6.6+/6.12 LTS line so `jb_iter_init_02` is not hit by the 6.1 verifier budget. Smallest test: `jibril` standalone, expect `72/76` (6.18, measured) or `52/76` (6.1, measured) before the files-object fix.

## Raw log index

All runs are committed under `frontier/out/` (force-added past the repo's `out/` ignore rule) so every count can be recomputed from the events; `compare.json` is reproducible with `python3 guest/compare.py cgrec.jsonl audit.log`.

- `out/a1-20261017T004710Z/out/`: Modal run 2 (authoritative A1/A2): `probe.log`, `kconfig.txt`, `kernel-surfaces.txt`, `bpftool-feature.txt`, `type-probe.jsonl`, `jibril-sections.txt`, `jibril-progs.jsonl`, `jibril-run.log` + `.clean.log`, `cgrec.jsonl`, `audit.log`, `compare.json`, `overhead.txt`, `jibril.sha256`, `release-tree.txt`.
- `out/a1-20261017T005823Z/out/`: Modal run 3 (constructed external BTF): `type-probe-custombtf.jsonl`, `jibril-progs-custombtf.jsonl`.
- `out/a1-20261017T004428Z/out/`: Modal run 1 (failed cgrec verifier log, jibril `--log-level` misuse); kept for the error lines.
- `out/vercel-20261017T0048Z/out/`: Vercel: `probe.log`, `uname.txt`, `kernel-surfaces.txt`, `bpftool-feature.txt`, `type-probe.jsonl`, `jibril-progs.jsonl`, `jibril-run.log` + `.clean.log`, `cgrec.jsonl`, `overhead.txt`, `pcrec-summary.json` (failed self-feedback run); `out2/`: `ns.txt`, `pcrec-summary.json` (working fanotify run).
- `out/a1-run{1,2,3-btf}.log`: driver stdout.
Redaction: logs contain no credentials (only the local stub token string "stub" and BPF map names such as `jb_slctokens_t`).

## Digest

- Works today, no kernel change: destinations + pid/tgid/comm from cgroup hooks on Modal and Vercel (19/19 vs audit, ~0-8% overhead); 12 of Jibril's cgroup_skb programs load; audit on Modal; fanotify exec/open paths on Vercel.
- Needs a Jibril change: non-fatal per-program loading with declared coverage, `btf_custom_path` support, a cgroup connect/sendmsg/sock_create fallback object, proc-connector/procfs process source; and the `jb_iter_init_02` split for 6.1 (52/76 -> expected 72/76).
- Needs the vendor: BTF + tracefs + tracepoints/kprobes (`DEBUG_INFO_BTF`, `FTRACE*`, `KPROBES`, `BPF_EVENTS`) on Modal and Vercel, plus audit netlink and init-pid-ns on Vercel; `MODULES`+ftrace (ideally a newer LTS) in E2B's `fc-kernels`. Without them, exec/argv/file capture cannot come from the kernel in any of the three guests.
