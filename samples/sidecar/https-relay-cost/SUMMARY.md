# Sidecar receipts: https

18 VM sandboxes in 66s wall; cells: invm=6, none=6, sidecar=6.

## Agreement (sidecar cell, n=6): agree=6

### https: common hosts (>=90% of 6 runs): `registry.npmjs.org`

## 6 runs reached only their group's common hosts; 0 reached something new


Evidence-derived allowlist (union of relayed hosts over 6 real runs): `registry.npmjs.org`

Original destination (SO_ORIGINAL_DST) visible to the Sidecar in 0 of 6 runs.

## Per-connection cost: sequential HTTPS GETs (new TCP connection each), seconds per request

| cell | sandboxes | requests | total p50 | total p95 | connect p50 | connect p95 | non-200 |
|---|---|---|---|---|---|---|---|
| invm | 6 | 1200 | 0.106 | 0.147 | 0.003 | 0.004 | 0 |
| none | 6 | 1200 | 0.111 | 0.158 | 0.002 | 0.003 | 0 |
| sidecar | 6 | 1200 | 0.112 | 0.155 | 0.002 | 0.002 | 0 |

## Workload outcomes

- invm: 6 of 6 exited 0
- none: 6 of 6 exited 0
- sidecar: 6 of 6 exited 0

## Cost (seconds per sandbox, p50 / p95, n per cell)

| phase | invm | none | sidecar |
|---|---|---|---|
| sandbox create | 0.2 / 0.334 (n=6) | 0.28 / 0.34 (n=6) | 0.07 / 0.082 (n=6) |
| sidecar up (create + listening) | - | - | 0.76 / 0.874 (n=6) |
| first exec | 0.96 / 1.822 (n=6) | 1.15 / 1.228 (n=6) | 1.11 / 1.267 (n=6) |
| arm in-VM recorder | 0.39 / 0.587 (n=6) | - | 0.29 / 0.365 (n=6) |
| workload | 22.93 / 49.373 (n=6) | 37.89 / 60.33 (n=6) | 29.5 / 60.297 (n=6) |
| build in-VM receipt | 0.49 / 1.032 (n=6) | - | 0.19 / 0.37 (n=6) |
| collect sidecar log | - | - | 0.05 / 0.198 (n=6) |
| total | 26.24 / 51.104 (n=6) | 39.81 / 62.069 (n=6) | 31.96 / 62.867 (n=6) |

In-VM receipts declared incomplete: 0; in-VM receipt missing: 0.
