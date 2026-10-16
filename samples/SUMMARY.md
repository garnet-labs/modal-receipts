# Sandbox receipts: https://github.com/pallets/click

100 recorded runs, 100 unrecorded runs, 44s wall for the whole cohort.
Receipts: 100 declared complete, 0 declared incomplete, 0 no receipt.

## 97 runs contacted the same 2 hosts. 3 contacted something new.

- `files.pythonhosted.org | pypi.org:443`
- `github.com:443`

- run 000 (constructed): `httpbin.org:443` via `bash > python3`
- run 001 (constructed): `httpbin.org:443` via `bash > python3`
- run 002 (constructed): `httpbin.org:443` via `bash > python3`

## Cost (seconds, per sandbox)

| phase | recorded | unrecorded |
|---|---|---|
| sandbox create | median 0.08 / p95 0.35 | median 0.08 / p95 0.25 |
| first exec | median 0.89 / p95 1.37 | median 0.9 / p95 1.18 |
| arm recorder | median 0.32 / p95 0.61 | - |
| workload | median 6.47 / p95 7.9 | median 6.44 / p95 8.49 |
| build receipt | median 0.44 / p95 1.17 | - |
| total | median 8.41 / p95 10.45 | median 7.71 / p95 9.6 |

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
- `/tmp/pip-build-env-1xmz5777`: 67 paths
- `/usr/local`: 54 paths
- `/tmp/pytest-of-root`: 18 paths
- `/tmp/pip-build-tracker-rs0_2ixr`: 8 paths
- `/tmp/pip-unpack-6elfxoe2`: 6 paths
- `/tmp/pip-ephem-wheel-cache-5snkhe4o`: 3 paths
- `/tmp/pip-modern-metadata-77p8pfak`: 3 paths
