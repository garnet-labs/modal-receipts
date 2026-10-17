# FACTS — Devin Outpost worker on E2B Embed (operator kernel 6.18) recorded by Jibril, one real session (n = 1)

All times UTC, 2026-10-17. Sources: `events.jsonl` (driver: fleet API + worker log), Devin v3 API (session, messages, events), `jibril.profile.json`, `run.json`.

## What ran
- E2B Embed (open-source E2B Runtime) self-hosted on the Devin cloud VM: `e2b-dev/runtime` HEAD `be9ec3e`, `embed/compose`, `docker compose up -d --wait` in 1 m 51 s (Docker Hub images pre-pulled via `mirror.gcr.io` to dodge 429s). Stock guest kernel `vmlinux-6.1.177_5008931`.
- Operator kernel: `amazonlinux/linux` tag `microvm-kernel6.18-6.18.36-71.136.amzn2023` (6.18.36), E2B's `6.1.177.config` carried forward with `make olddefconfig` plus `MODULES BPF_JIT BPF_JIT_ALWAYS_ON FTRACE_SYSCALLS KPROBES KPROBE_EVENTS KALLSYMS_ALL`; `make -j8 vmlinux` 5 m 07 s on 8 vCPU; `vmlinux.bin` 48,753,968 B, sha256 `9e2e248aa4204a5c42804072cda121a731c1a2c04ebc4e84d8c80524afc886bc`, BTF present. Installed as `/fc-kernels/vmlinux-6.18-garnet/amd64/vmlinux.bin`; `compose.override.yaml` sets `DEFAULT_KERNEL_VERSION: vmlinux-6.18-garnet` on `orchestrator` + `api`; `docker compose up -d --wait` 1 m 33 s. Template `garnet-outpost` (`8fa4kx7hjrf36mgr2add`, from `base`, 2 vCPU / 2048 MiB) built in 6.2 s; guest boots `6.18.36+` with `/sys/kernel/btf/vmlinux`, syscalls tracefs, `CONFIG_BPF_JIT=y KPROBES=y MODULES=y FTRACE_SYSCALLS=y`.
- Guest setup at runtime (`e2b/guest-setup.sh`, 28–30 s): official Devin CLI 3000.11.92 via `cli.devin.ai/install.sh`, Jibril v2.17.0 tarball (sha256 `7a5160e4…423f` verified), ffmpeg/jq.
- Jibril (`e2b/jibril.yaml`, `GARNET_SAR=true`, jsonprofiler only): ready in 4.3 s, **76 programs / 72 attached / 37 live links / 0 errors** (`/var/run/jibril/ebpf.status.json`).
- Worker: `devin worker start --outpost=garnet-receipts --once --poll-interval-secs 5` started as an envd background command with the token in its env; `Worker started!` 10.2 s after start.
- Session `devin-d7fac4db7cf449668cf49afe52d79539` (Lite, created via v3 API with `platform="garnet-receipts"` at 01:16:45): first tool call 01:16:53 exited **228 — the 2.4 GB guest rootfs was 100 % full**; Devin diagnosed it (`df`, `du`, `find -size +50M`), deleted the serve-web bundle its own remote had downloaded, re-ran `npm init -y && npm install left-pad` (exit 0), verified, replied `done` at 01:17:18. Parent slept it 01:17:40; remote exited; `--once` worker exited 01:17:46; Jibril SIGINT → profile written; sandbox killed. Cost $0.0415.

## Numbers (n = 1)
| step | value |
|---|---|
| template build (new kernel) | 6.2 s |
| Sandbox.create | 0.087 s |
| guest setup (CLI + Jibril download) | 29.2 s |
| Jibril start → 72/76 attached | 4.28 s |
| worker start → registered | 10.2 s |
| session create → Devin done | 33 s (includes the disk-full retry) |
| sleep → worker exit | ≈6 s |
| profile collect | 4.7 s |
| kernel build | 5 m 07 s (8 vCPU) |

## Profile (right side of `paired-outpost-record-e2b.html`)
- `network.egress`: 12 domains, 19 connections, each peer with `proc_trees` ancestry: `registry.npmjs.org` ← `systemd > envd > devin > devin-remote > bash > node`; `git-manager.devin.ai` / `github.com` ← `… > git > git-remote-http`; `api.devin.ai`, `static.devin.ai`, sentry ← `devin`; `outpost-gateway.devin.ai`, plugin-bundle S3 ← `devin-remote`; `windsurf-stable.codeiumdata.com`, `server.codeium.com` ← `curl`; `events.e2b.local` = E2B's own guest telemetry (envd → host).
- Same host set as the Modal receipt (minus the per-host bytes the Sidecar measured, plus E2B's envd endpoint). network_policy claim `{"enabled": false, "allow": []}`.
- Coverage from the loader's own counters (76/72/0). Jibril's status file has no lost-event counter — completeness beyond "0 errors" is not claimed.

## Blockers / fixes found
1. **Guest disk**: base template rootfs is 2.4 GB; Devin's remote downloads ~0.5 GB (devin-remote, serve-web bundle, plugins) and Jibril's raw-event printer wrote 441k lines → run 1 (sandbox `icweufpmpag29u798hex2`, session `devin-46c5ed42…`) ended with an **empty profile** ("no space left on device"). Run 2 dropped the raw printer; `Template.build(min_free_disk_mb=8192)` did not enlarge the rootfs; the disk was still full during the session (Devin recovered by itself). Fix for real use: a template with a larger rootfs (E2B template disk size), or `/var/log/jibril` on tmpfs.
2. Embed caps `Sandbox.create(timeout=…)` at 1 h (400 above).
3. envd keeps a foreground exec open while any child holds its pipes: start Jibril and the worker with `commands.run(..., background=True, timeout=0)`.
4. Jibril's `jibril.status.json` has no eBPF section; loader counts are in `ebpf.status.json` under `"ebpf"`.
5. `e2b` SDK raises `CommandExitException` on non-zero exit.

## Not done
- No Sidecar-style second vantage on E2B (E2B's host-side nftables/SNI view was not pulled) — the record is guest-side only.
- n = 1; no overhead measurement.
