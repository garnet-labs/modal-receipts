# Sandbox receipts: install

100 recorded runs, 0 unrecorded runs, 104s wall for the whole cohort.
Receipts: 100 declared complete, 0 declared incomplete, 0 no receipt.

## 94 runs contacted only their group's common hosts (2 across 2 groups). 6 contacted something new.

- `npm: registry.npmjs.org:443`
- `pip: files.pythonhosted.org | pypi.org:443`

- run 023 [npm:puppeteer]: `storage.googleapis.com:443` via `bash > node > sh > node`
- run 025 [npm:cypress]: `cdn.cypress.io | download.cypress.io:443` via `bash > node > sh > node`
- run 026 [npm:sqlite3]: `github.com:443` via `bash > node > sh > node`
- run 026 [npm:sqlite3]: `release-assets.githubusercontent.com:443` via `bash > node > sh > node`
- run 029 [npm:canvas]: `github.com:443` via `bash > node > sh > node`
- run 029 [npm:canvas]: `release-assets.githubusercontent.com:443` via `bash > node > sh > node`
- run 038 [npm:node-sass]: `github.com:443` via `bash > node > sh > node`
- run 038 [npm:node-sass]: `nodejs.org:443` via `bash > node > sh > node > node`
- run 046 [npm:serverless]: `install.serverless.com:443` via `bash > node > sh > node`

## Workload outcomes

98 of 100 (label, recorded) groups exited 0. Non-zero: npm:better-sqlite3=[1], npm:fsevents=[1]

## Cost (seconds, per sandbox)

| phase | recorded | unrecorded |
|---|---|---|
| sandbox create | median 0.12 / p95 0.36 | - |
| first exec | median 1.03 / p95 2.61 | - |
| arm recorder | median 0.39 / p95 0.72 | - |
| workload | median 3.24 / p95 17.0 | - |
| build receipt | median 0.5 / p95 1.26 | - |
| total | median 6.2 / p95 19.04 | - |

## Coverage, as declared by the kernel (first complete receipt)

```json
{
 "recorder": "linux-audit",
 "kernel": "7.2.9",
 "kernel_counters_at_stop": {
  "enabled": "1",
  "failure": "1",
  "lost": "0",
  "backlog": "0",
  "backlog_limit": "65536",
  "backlog_wait_time_actual": "0"
 },
 "declared_complete": true,
 "scope": "every connect/execve/clone/exit/open-for-write/unlink/rename syscall in this VM since arming; names from the sandbox's own DNS answers; recorder processes excluded"
}
```

## Files touched (first complete receipt)

- `/root/.npm`: 3 paths
- `/`: 1 paths
- `/work`: 1 paths
- `/work/`: 1 paths
- `/work/install.log`: 1 paths
- `/work/results`: 1 paths
