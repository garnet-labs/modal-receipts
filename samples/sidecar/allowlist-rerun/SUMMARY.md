# Sidecar receipts: install

11 VM sandboxes in 15s wall; cells: sidecar=11.

## Agreement (sidecar cell, n=11): agree=11

### npm: common hosts (>=90% of 7 runs): `registry.npmjs.org`

### pip: common hosts (>=90% of 3 runs): `files.pythonhosted.org`, `pypi.org`

## 8 runs reached only their group's common hosts; 2 reached something new

- run 004 [npm:canvas]: `github.com` via `bash > node > sh > node`
- run 004 [npm:canvas]: `release-assets.githubusercontent.com` via `bash > node > sh > node`
- run 003 [npm:puppeteer]: `storage.googleapis.com` via `bash > node > sh > node`
- run 010 [constructed:curl-example.com] (constructed): `(no SNI)` {'refused_no_sni': 1}; `example.com` refused_by_policy (sidecar.outbound_domain_allowlist (evidence-derived: union of Sidecar-relayed hosts over 30 real runs (out-sidecar30/allowlist.json))): upstream TCP opened, 517 B sent (ClientHello), 0 B returned; curl rc=35 (curl: (35) OpenSSL SSL_connect: SSL_ERROR_SYSCALL in connection to example.com:443)

Evidence-derived allowlist (union of relayed hosts over 10 real runs): `files.pythonhosted.org`, `github.com`, `pypi.org`, `registry.npmjs.org`, `release-assets.githubusercontent.com`, `storage.googleapis.com`

## Allowlist rerun: sidecar outbound_domain_allowlist = ['cdn.cypress.io', 'download.cypress.io', 'files.pythonhosted.org', 'github.com', 'install.serverless.com', 'nodejs.org', 'pypi.org', 'registry.npmjs.org', 'release-assets.githubusercontent.com', 'storage.googleapis.com']
10 of 10 real runs exited 0 with the allowlist on.

Original destination (SO_ORIGINAL_DST) visible to the Sidecar in 0 of 11 runs.

## Workload outcomes

- sidecar: 11 of 11 exited 0

## Cost (seconds per sandbox, p50 / p95, n per cell)

| phase | sidecar |
|---|---|
| sandbox create | 0.11 / 0.35 (n=10) |
| sidecar up (create + listening) | 0.69 / 1.006 (n=10) |
| first exec | 0.93 / 1.242 (n=10) |
| arm in-VM recorder | 0.32 / 0.53 (n=10) |
| workload | 2.28 / 6.933 (n=10) |
| build in-VM receipt | 0.23 / 0.779 (n=10) |
| collect sidecar log | 0.1 / 0.392 (n=10) |
| total | 4.8 / 11.221 (n=10) |

In-VM receipts declared incomplete: 0; in-VM receipt missing: 0.
