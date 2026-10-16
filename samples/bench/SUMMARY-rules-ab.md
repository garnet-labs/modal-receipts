# Sandbox receipts: bench-rules

40 recorded runs, 40 unrecorded runs, 74s wall for the whole cohort.
Receipts: 40 declared complete, 0 declared incomplete, 0 no receipt.

## 20 runs contacted the same 0 hosts. 20 contacted something new.


- run 000 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 000 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 001 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 001 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 002 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 002 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 003 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 003 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 004 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 004 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 005 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 005 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 006 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 006 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 007 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 007 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 008 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 008 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 009 [bench:repo]: `github.com:443` via `bash > git > git > git-remote-http`
- run 009 [bench:repo]: `registry.npmjs.org:443` via `bash > node`
- run 010 [bench:repo:nofiles]: `github.com:443` via `bash > git > git > git-remote-http`
- run 010 [bench:repo:nofiles]: `registry.npmjs.org:443` via `bash > node`
- run 011 [bench:repo:nofiles]: `github.com:443` via `bash > git > git > git-remote-http`
- run 011 [bench:repo:nofiles]: `registry.npmjs.org:443` via `bash > node`
- run 012 [bench:repo:nofiles]: `github.com:443` via `bash > git > git > git-remote-http`
- run 012 [bench:repo:nofiles]: `registry.npmjs.org:443` via `bash > node`
- run 013 [bench:repo:nofiles]: `github.com:443` via `bash > git > git > git-remote-http`
- run 013 [bench:repo:nofiles]: `registry.npmjs.org:443` via `bash > node`
- run 014 [bench:repo:nofiles]: `github.com:443` via `bash > git > git > git-remote-http`
- run 014 [bench:repo:nofiles]: `registry.npmjs.org:443` via `bash > node`
- run 015 [bench:repo:nofiles]: `github.com:443` via `bash > git > git > git-remote-http`
- run 015 [bench:repo:nofiles]: `registry.npmjs.org:443` via `bash > node`
- run 016 [bench:repo:nofiles]: `github.com:443` via `bash > git > git > git-remote-http`
- run 016 [bench:repo:nofiles]: `registry.npmjs.org:443` via `bash > node`
- run 017 [bench:repo:nofiles]: `github.com:443` via `bash > git > git > git-remote-http`
- run 017 [bench:repo:nofiles]: `registry.npmjs.org:443` via `bash > node`
- run 018 [bench:repo:nofiles]: `github.com:443` via `bash > git > git > git-remote-http`
- run 018 [bench:repo:nofiles]: `registry.npmjs.org:443` via `bash > node`
- run 019 [bench:repo:nofiles]: `github.com:443` via `bash > git > git > git-remote-http`
- run 019 [bench:repo:nofiles]: `registry.npmjs.org:443` via `bash > node`

## Workload outcomes

80 of 80 (label, recorded) groups exited 0.

## Bench: workload seconds, recorded vs unrecorded

| profile | recorded median / p95 | unrecorded median / p95 | audit log bytes (median) |
|---|---|---|---|
| bench:files | 5.5 / 6.92 | 0.5 / 0.71 | 3684975 |
| bench:files:nofiles | 0.57 / 1.24 | 0.45 / 0.71 | 66283 |
| bench:repo | 7.31 / 10.34 | 6.78 / 9.53 | 524037 |
| bench:repo:nofiles | 7.37 / 12.49 | 6.49 / 7.98 | 156833 |

## Cost (seconds, per sandbox)

| phase | recorded | unrecorded |
|---|---|---|
| sandbox create | median 0.14 / p95 0.55 | median 0.07 / p95 0.29 |
| first exec | median 1.03 / p95 1.49 | median 0.99 / p95 1.23 |
| arm recorder | median 0.36 / p95 0.88 | - |
| workload | median 5.64 / p95 10.03 | median 2.69 / p95 8.51 |
| build receipt | median 0.46 / p95 1.83 | - |
| total | median 8.48 / p95 14.2 | median 3.97 / p95 9.61 |

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
 "scope": "every connect/execve/clone/exit syscall (file rules off) in this VM since arming; names from the sandbox's own DNS answers; recorder processes excluded"
}
```

## Files touched (first complete receipt)

