# Sandbox receipts: bench

40 recorded runs, 40 unrecorded runs, 31s wall for the whole cohort.
Receipts: 40 declared complete, 0 declared incomplete, 0 no receipt.

## 30 runs contacted the same 0 hosts. 10 contacted something new.


- run 030 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 030 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 031 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 031 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 032 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 032 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 033 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 033 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 034 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 034 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 035 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 035 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 036 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 036 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 037 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 037 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 038 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 038 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 039 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 039 [bench:repo]: `registry.npmjs.org:443` via `bash > node`

## Workload outcomes

80 of 80 (label, recorded) groups exited 0.

## Bench: workload seconds, recorded vs unrecorded

| profile | recorded median / p95 | unrecorded median / p95 | audit log bytes (median) |
|---|---|---|---|
| bench:files | 5.6 / 7.43 | 0.54 / 0.77 | 3461265 |
| bench:net | 0.24 / 3.2 | 0.26 / 0.95 | 1411783 |
| bench:procs | 2.93 / 3.65 | 2.71 / 3.03 | 2563496 |
| bench:repo | 7.32 / 8.23 | 5.33 / 7.47 | 524037 |

## Cost (seconds, per sandbox)

| phase | recorded | unrecorded |
|---|---|---|
| sandbox create | median 0.1 / p95 0.31 | median 0.16 / p95 0.38 |
| first exec | median 0.99 / p95 1.32 | median 0.99 / p95 1.43 |
| arm recorder | median 0.38 / p95 0.6 | - |
| workload | median 4.35 / p95 7.8 | median 1.73 / p95 7.27 |
| build receipt | median 0.52 / p95 1.6 | - |
| total | median 7.32 / p95 10.87 | median 3.62 / p95 8.84 |

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

- `/`: 1 paths
- `/work`: 1 paths
