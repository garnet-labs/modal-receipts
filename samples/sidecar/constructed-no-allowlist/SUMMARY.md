# Sidecar receipts: install

2 VM sandboxes in 8s wall; cells: sidecar=2.

## Agreement (sidecar cell, n=2): agree=2

### npm: common hosts (>=90% of 1 runs): `registry.npmjs.org`

## 1 runs reached only their group's common hosts; 0 reached something new

- run 001 [constructed:curl-example.com] (constructed): `(no SNI)` {'refused_no_sni': 1}; `example.com` {'relayed': 1}; curl rc=0 (no stderr)

Evidence-derived allowlist (union of relayed hosts over 1 real runs): `registry.npmjs.org`

Original destination (SO_ORIGINAL_DST) visible to the Sidecar in 0 of 2 runs.

## Workload outcomes

- sidecar: 2 of 2 exited 0

## Cost (seconds per sandbox, p50 / p95, n per cell)

| phase | sidecar |
|---|---|
| sandbox create | 0.09 / 0.089 (n=1) |
| sidecar up (create + listening) | 0.74 / 0.74 (n=1) |
| first exec | 0.88 / 0.883 (n=1) |
| arm in-VM recorder | 0.32 / 0.318 (n=1) |
| workload | 0.98 / 0.98 (n=1) |
| build in-VM receipt | 0.16 / 0.164 (n=1) |
| collect sidecar log | 0.07 / 0.067 (n=1) |
| total | 3.31 / 3.309 (n=1) |

In-VM receipts declared incomplete: 0; in-VM receipt missing: 0.
