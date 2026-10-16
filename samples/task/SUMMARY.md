# Sandbox receipts: https://github.com/pallets/click

3 recorded runs, 2 unrecorded runs, 14s wall for the whole cohort.
Receipts: 3 declared complete, 0 declared incomplete, 0 no receipt.

## 2 runs contacted the same 2 hosts. 1 contacted something new.

- `files.pythonhosted.org:443`
- `github.com:443`

- run 000 (constructed): `httpbin.org:443` via `bash > python3`

## Cost (seconds, per sandbox)

| phase | recorded | unrecorded |
|---|---|---|
| sandbox create | median 0.08 / p95 0.14 | median 0.45 / p95 0.59 |
| first exec | median 1.16 / p95 1.27 | median 1.12 / p95 1.36 |
| arm recorder | median 0.27 / p95 0.33 | - |
| workload | median 6.95 / p95 7.21 | median 6.49 / p95 7.36 |
| build receipt | median 0.4 / p95 0.43 | - |
| total | median 8.96 / p95 9.11 | median 8.06 / p95 9.32 |

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

- `/work/repo`: 3503 paths
- `/tmp/pip-build-env-f6jemn4w`: 67 paths
- `/usr/local`: 54 paths
- `/tmp/pytest-of-root`: 18 paths
- `/tmp/pip-build-tracker-d0zuo853`: 8 paths
- `/garnet/state`: 7 paths
- `/tmp/pip-unpack-hqce2tcj`: 6 paths
- `/tmp/pip-ephem-wheel-cache-9a7718if`: 3 paths
