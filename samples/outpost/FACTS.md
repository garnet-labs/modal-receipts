# FACTS — Devin Outpost worker on Modal, one real session, one receipt (n = 1)

All times UTC, 2026-10-17. Sources: driver `events.jsonl` (fleet API + worker log), Devin v3 API (session, messages, events), `receipt.json`, Modal CLI/SDK 1.6.2.

## What ran
- Outpost `garnet-receipts` (`outpost_env-72393f54087644a59b31bae50b9686cb`, account-scoped, created by Farrukh ~00:30) — token = org secret `DEVIN_OUTPOST_SECRET` (service user `outpost-garnet-receipts`); `DEVIN_OUTPOST_TOKEN` is expired/revoked (401). Token reached the sandbox only as a `modal.Secret.from_dict` built from the driver's environment; never on argv or in logs.
- Modal: app `ap-YIyksywau0k9e6efZUUUul` (workspace jadoonf/main), image `im-qkYyHwGQgdokojElg0Tyfb` = ubuntu:24.04 + git/ffmpeg/auditd/python3/nodejs/npm + official Devin CLI 3000.11.92 (`cli.devin.ai/install.sh`; the installer exits 1 after a login prompt it cannot show — tolerated, binary verified). Sandbox `sb-01M53MT4DJYHSYRD9RYB2Z0QM6`: `runtime="vm"`, kernel 7.2.9, 4 vCPU, 4944 MiB visible (4096 + 1024 Sidecar reserve), timeout 2 h; Sidecar `garnet` (`experimental_options={"proxy_traffic_via_sidecar": "garnet"}`) fail-closed: driver waited for :443 to listen before anything else ran.
- Worker: `devin worker start --outpost=garnet-receipts --once --poll-interval-secs 5` (official CLI). Log: `worker worker-384e201a… starting` → `serving outpost garnet-receipts (outpost_env-…)` → `Worker started! Now you can launch sessions on the webapp` at 00:40:00.9.
- Session: created by the parent session through the v3 API (`devin_session_create`, `platform="garnet-receipts"`, Lite) at 00:42:28 → `devin-85ca56e38aee4ec894263fd673552650`. No web UI needed: `POST /v3/organizations/{org}/sessions` takes `platform` = outpost pool name (docs: api-reference/v3/sessions/post-organizations-sessions).
- Devin did exactly the prompt: one shell call `cd /tmp && rm -rf modal-receipts && git clone … && cd modal-receipts && python3 -m py_compile sidecar_receipts.py && npm init -y && npm install left-pad`, exit 0 (00:42:35.4 → 00:42:37.8), replied `done` 00:42:40. Parent put it to sleep 00:44:10; devin-remote exited 00:44:11; `--once` worker exited; queue entry released 00:44:12. Cost: 0.0 ACU, $0.054 on-demand.

## Numbers (n = 1)
| step | value |
|---|---|
| Sandbox.create | 0.17 s |
| Sidecar listening (fail-closed gate) | 1.5 s |
| recorder arm (audit rules + DNS forwarder) | 0.58 s |
| sandbox create → worker registered | ≈5.3 s |
| session create → claimed → connected → first command | 2.2 s → 2.5 s → 1.9 s (00:42:28.8 / 30.9 / 33.5 / 35.4) |
| first command → Devin "done" | 4.6 s |
| receipt build (in VM) | 3.0 s |
| Sidecar relay overhead | not re-measured (earlier series: +1 ms/conn p50) |
| worker image build | apt layer 112 s, CLI layer 11 s (cached after) |

## Receipt (right side of the paired record)
- Verdict **agree**: 12 hosts seen by both Sidecar and in-VM record, 0 Sidecar-only, 0 in-VM-only; kernel `lost=0`, backlog 0, declared complete; 11,539 syscall records over 586 s; 622 processes executed; 6,218 paths written.
- Hosts ← chain: `api.devin.ai`, `static.devin.ai`, sentry ← `devin` (worker); `outpost-gateway.devin.ai`, plugin-bundle S3 ← `devin-remote`; `github.com` ← `devin-remote > git` (clone of `CognitionAI/devin-marketplace`); `git-manager.devin.ai` ← `node > bash > git > git-remote-http` (the session's `git clone` was rewritten by Devin to its proxy, with a credential-store file shredded at session end); `registry.npmjs.org` ← `node` (npm install left-pad); `windsurf-stable.codeiumdata.com` 208 MB ← `devin-remote > bash > curl` (serve-web bundle); codeium.com hosts ← `devin` + `curl`.
- network_policy in the queue entry: `{"enabled": false, "allow": []}` — nothing to enforce; the receipt is the only record of what the machine reached. Reference: "enforcing it on your machines is the outpost operator's responsibility."
- "Workload passed" = Devin's exit code 0 + `/tmp/modal-receipts/.git` and `package.json` present at teardown. "Capture complete" = recorder counters + agreement. Kept separate; nothing constructed.

## Blockers / fixes found
1. **Recorder bug (fixed in this PR):** auditd rotated `audit.log` at 8 MB (00:42:37) and `guest/receipt.py` read only the live file → first receipt said `in_vm_record_incomplete_or_altered` with 10 Sidecar-only hosts. Fix: `receipt.py` reads `audit.log.N` oldest-first and lists `capture.log_files`; `recorder.sh` sets `max_log_file_action = IGNORE`, `max_log_file = 2048`. Rebuilt in the same VM → agree. The v1 receipt file was overwritten by the rebuild; its summary (verdict `in_vm_record_incomplete_or_altered`, both = sentry + registry.npmjs.org, Sidecar-only = api.devin.ai, plugin-bundle S3, git-manager.devin.ai, github.com, outpost-gateway.devin.ai, server/unleash/windsurf-stable.codeium.com, static.devin.ai, windsurf-stable.codeiumdata.com; 3,338 syscall records from the live file only) is recorded here and in `events.jsonl`/driver log.
2. **Driver bug (fixed):** `pgrep -f 'devin worker start'` matched its own shell → loop never saw the worker exit; `outpost_finish.py` added to finish a run from a reconnected sandbox/sidecar handle.
3. Modal partner integration (`modal-devin`, alpha) needs an admin-scoped Enterprise service-user key; not usable with this token → self-orchestrated. E2B partner template similarly needs a `cog_` v3 service-user token with Manage outposts.
4. Fleet API `GET /opbeta/outposts/devins/{session_id}` → 404 once the session is released; read the queue entry while claimed.
5. Observation (no incident): devin-remote logs the session's exec-env variable *names* (org secrets are injected onto the outpost machine) with values shown as `[REDACTED]` by devin-remote itself. The attached worker-log excerpt omits those lines.

## Not done
- E2B Embed + 6.18 kernel + Jibril variant (secondary) — not started in this lane yet.
- Sidecar overhead not re-measured; n = 1 for every number above.
