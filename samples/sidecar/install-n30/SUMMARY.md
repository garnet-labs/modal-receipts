# Sidecar receipts: install

90 VM sandboxes in 108s wall; cells: sidecar=30, invm=30, none=30.

## Agreement (sidecar cell, n=30): agree=30

### npm: common hosts (>=90% of 20 runs): `registry.npmjs.org`

### pip: common hosts (>=90% of 10 runs): `files.pythonhosted.org`, `pypi.org`

## 24 runs reached only their group's common hosts; 6 reached something new

- run 011 [npm:sqlite3]: `github.com` via `bash > node > sh > node`
- run 011 [npm:sqlite3]: `release-assets.githubusercontent.com` via `bash > node > sh > node`
- run 014 [npm:serverless]: `install.serverless.com` via `bash > node > sh > node`
- run 009 [npm:puppeteer]: `storage.googleapis.com` via `bash > node > sh > node`
- run 012 [npm:canvas]: `github.com` via `bash > node > sh > node`
- run 012 [npm:canvas]: `release-assets.githubusercontent.com` via `bash > node > sh > node`
- run 010 [npm:cypress]: `cdn.cypress.io` via `bash > node > sh > node`
- run 010 [npm:cypress]: `download.cypress.io` via `bash > node > sh > node`
- run 013 [npm:node-sass]: `github.com` via `bash > node > sh > node`
- run 013 [npm:node-sass]: `nodejs.org` via `bash > node > sh > node > node`

Evidence-derived allowlist (union of relayed hosts over 30 real runs): `cdn.cypress.io`, `download.cypress.io`, `files.pythonhosted.org`, `github.com`, `install.serverless.com`, `nodejs.org`, `pypi.org`, `registry.npmjs.org`, `release-assets.githubusercontent.com`, `storage.googleapis.com`

Original destination (SO_ORIGINAL_DST) visible to the Sidecar in 0 of 30 runs.

## Workload outcomes

- sidecar: 30 of 30 exited 0
- invm: 30 of 30 exited 0
- none: 30 of 30 exited 0

## Cost (seconds per sandbox, p50 / p95, n per cell)

| phase | sidecar | invm | none |
|---|---|---|---|
| sandbox create | 0.08 / 0.32 (n=30) | 0.14 / 0.437 (n=30) | 0.09 / 0.296 (n=30) |
| sidecar up (create + listening) | 0.73 / 1.133 (n=30) | - | - |
| first exec | 0.98 / 1.751 (n=30) | 1.08 / 1.758 (n=30) | 1.03 / 1.445 (n=30) |
| arm in-VM recorder | 0.31 / 0.512 (n=30) | 0.4 / 0.573 (n=30) | - |
| workload | 3.05 / 36.083 (n=30) | 3.02 / 32.362 (n=30) | 3.5 / 40.208 (n=30) |
| build in-VM receipt | 0.25 / 1.513 (n=30) | 0.44 / 0.964 (n=30) | - |
| collect sidecar log | 0.08 / 0.358 (n=30) | - | - |
| total | 6.01 / 38.511 (n=30) | 5.61 / 35.25 (n=30) | 4.52 / 41.875 (n=30) |

In-VM receipts declared incomplete: 0; in-VM receipt missing: 0.
