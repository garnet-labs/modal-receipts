# Harbor live pilot — 2026-11-20 UTC

Harbor 0.26.0, Modal 1.6.4, workspace `jadoonf`, image builder `2025.06` selected
with `MODAL_IMAGE_BUILDER_VERSION` (no account setting changes). `summary.json`
contains timestamps and phase timings. The four receipt files are host-side
`garnet-receipt.json` outputs, copied without agent traces or credential-bearing
config files. Secret-value checks found no provisioned key/token values in them.
These are network evidence, not process attribution or TLS content inspection.

## Dataset and commands

The requested `terminal-bench/terminal-bench@4.1.0` Hub package resolves, but its
66 tasks include none of `fix-git`, `regex-log`, `log-summary-date-ranges`.
For this small-task pilot we used the legacy `terminal-bench@2.0` registry
dataset containing those tasks, without modifying task files or Harbor.

```sh
export MODAL_IMAGE_BUILDER_VERSION=2025.06
harbor run -d terminal-bench@2.0 \
  -e modal_receipts.harbor:GarnetModalEnvironment \
  -a oracle -i fix-git -n 1 -k 1

harbor run -d terminal-bench@2.0 \
  -e modal_receipts.harbor:GarnetModalEnvironment \
  -a claude-code -m anthropic/claude-sonnet-5 \
  --base-url https://ai-gateway.vercel.sh \
  --ae ANTHROPIC_AUTH_TOKEN="$AI_GATEWAY_API_KEY" \
  -i fix-git -i regex-log -i log-summary-date-ranges -n 2 -k 1
```

The baseline repeated the second command once, replacing the custom environment
with `-e modal`. Modal credentials were supplied through environment variables;
no credentials are included here. There were no agent retries.

## Results

| Task | Stock Claude wall (s) | Observer Claude wall (s) | Stock / observer reward | Observer distinct SNI hosts | Connections |
|---|---:|---:|---|---:|---:|
| fix-git | 110.411 | 116.917 | 1 / 1 | 9 | 26 |
| log-summary-date-ranges | 105.957 | 128.560 | 1 / 1 | 9 | 26 |
| regex-log | 171.026 | 224.519 | 1 / 1 | 9 | 28 |

Oracle `fix-git`: 56.507 s, reward 1, six distinct hosts, 15 connections.
All seven completed trials had no exception. All four observer receipts declared
`public` network policy and `observed_outside_policy: []`; that empty list is
expected under public policy and is not a security verdict. Host sets include
setup/verifier downloads as well as agent traffic. Claude receipts include both
`ai-gateway.vercel.sh` and `api.anthropic.com`; the SNI evidence alone does not
identify what requests those connections carried. Each receipt also includes one
loopback `refused_no_sni` connection from the Sidecar readiness probe; it is not
an agent connection. Start events are retained but excluded from connection counts.

**Not a controlled overhead benchmark:** stock Modal selected gVisor, while the
observer forces VM; observer reserves 1024 MiB extra memory (3072 vs 2048 MiB).
Runs overlapped and image caches, model responses and setup timings differ.
Job wall times: stock three-task job 4m37s; observer three-task job 5m41s.

## Resource accounting and failures

- Seven successful main Sandboxes: one Oracle, three observer Claude, three stock
  Claude; four native Sidecars (one per observer Sandbox).
- Trial wall times above include image/setup/API/teardown overhead; they are not
  Modal billing durations. Image builds add separate compute not measured here.
- Before selecting the modern builder, one Oracle and three stock Claude trials
  failed during image building, before Sandbox creation. The legacy builder
  installed `aiohttp==3.9.1` under Python 3.13 and failed with
  `error: [Errno 2] No such file or directory: 'gcc'`. No model rollout ran in
  those failed attempts. A 4.1.0 task-filter attempt also stopped before creation.
- Harbor's default deleting teardown was used. A final live `Sandbox.list()`
  returned **0 active workspace Sandboxes**. No further workloads were launched.

## Coverage

TCP/443 ClientHello SNI relay only, no TLS decryption. Not DNS, other ports, UDP,
TLS without SNI, or the Sidecar's outbound traffic. Open connections are logged
on completion and may be absent at collection. Policy comparison is hostname
and wildcard matching, not evaluation of IP/CIDR rules or proof of enforcement.
