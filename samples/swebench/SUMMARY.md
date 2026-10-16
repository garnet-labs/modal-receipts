# Sandbox receipts: swebench

5 recorded runs, 0 unrecorded runs, 15s wall for the whole cohort.
Receipts: 5 declared complete, 0 declared incomplete, 0 no receipt.

## 5 runs contacted only their group's common hosts (0 across 1 group). 0 contacted something new.



## Workload outcomes

5 of 5 (label, recorded) groups exited 0.

## Cost (seconds, per sandbox)

| phase | recorded | unrecorded |
|---|---|---|
| sandbox create | median 0.62 / p95 1.11 | - |
| first exec | median 1.2 / p95 1.69 | - |
| arm recorder | median 0.56 / p95 0.82 | - |
| workload | median 1.91 / p95 2.54 | - |
| build receipt | median 0.84 / p95 1.48 | - |
| total | median 6.32 / p95 10.91 | - |

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

- `/testbed/django`: 648 paths
- `/testbed/tests`: 16 paths
- `/opt/miniconda3`: 1 paths
- `/tmp/`: 1 paths
- `/tmp/v3h45mnj`: 1 paths
- `/work/`: 1 paths
- `/work/apply.log`: 1 paths
- `/work/results`: 1 paths
