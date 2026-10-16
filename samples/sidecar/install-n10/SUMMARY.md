# Sidecar receipts: install

30 VM sandboxes in 17s wall; cells: sidecar=10, invm=10, none=10.

## Agreement (sidecar cell, n=10): agree=10

### npm: common hosts (>=90% of 7 runs): `registry.npmjs.org`

### pip: common hosts (>=90% of 3 runs): `files.pythonhosted.org`, `pypi.org`

## 8 runs reached only their group's common hosts; 2 reached something new

- run 004 [npm:canvas]: `github.com` via `bash > node > sh > node`
- run 004 [npm:canvas]: `release-assets.githubusercontent.com` via `bash > node > sh > node`
- run 003 [npm:puppeteer]: `storage.googleapis.com` via `bash > node > sh > node`

Evidence-derived allowlist (union of relayed hosts over 10 real runs): `files.pythonhosted.org`, `github.com`, `pypi.org`, `registry.npmjs.org`, `release-assets.githubusercontent.com`, `storage.googleapis.com`

Original destination (SO_ORIGINAL_DST) visible to the Sidecar in 0 of 10 runs.

## Workload outcomes

- sidecar: 10 of 10 exited 0
- invm: 10 of 10 exited 0
- none: 10 of 10 exited 0

## Cost (seconds per sandbox, p50 / p95, n per cell)

| phase | sidecar | invm | none |
|---|---|---|---|
| sandbox create | 0.2 / 0.437 (n=10) | 0.23 / 0.298 (n=10) | 0.19 / 0.778 (n=10) |
| sidecar up (create + listening) | 0.76 / 1.104 (n=10) | - | - |
| first exec | 1.08 / 1.341 (n=10) | 1.06 / 1.298 (n=10) | 1.02 / 1.89 (n=10) |
| arm in-VM recorder | 0.43 / 0.629 (n=10) | 0.44 / 0.495 (n=10) | - |
| workload | 2.44 / 7.169 (n=10) | 2.42 / 6.742 (n=10) | 2.34 / 5.821 (n=10) |
| build in-VM receipt | 0.5 / 1.039 (n=10) | 0.53 / 0.671 (n=10) | - |
| collect sidecar log | 0.25 / 0.52 (n=10) | - | - |
| total | 6.64 / 12.76 (n=10) | 5.26 / 8.768 (n=10) | 5.06 / 6.848 (n=10) |

In-VM receipts declared incomplete: 0; in-VM receipt missing: 0.
