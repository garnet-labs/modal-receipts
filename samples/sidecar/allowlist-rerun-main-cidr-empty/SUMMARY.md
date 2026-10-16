# Sidecar receipts: install

4 VM sandboxes in 23s wall; cells: sidecar=4.

## Agreement (sidecar cell, n=4): agree=4

### npm: common hosts (>=90% of 2 runs): `registry.npmjs.org`

## 2 runs reached only their group's common hosts; 0 reached something new

- run 003 [constructed:curl-example.com] (constructed): `(no SNI)` {'refused_no_sni': 1}; `example.com` refused_by_policy (sidecar.outbound_domain_allowlist (evidence-derived: union of Sidecar-relayed hosts over 30 real runs (out-sidecar30/allowlist.json))): upstream TCP opened, 517 B sent (ClientHello), 0 B returned; curl rc=35 (curl: (35) OpenSSL SSL_connect: SSL_ERROR_SYSCALL in connection to example.com:443)
- run 002 [constructed:curl-http80-example.com] (constructed): `(no SNI)` {'refused_no_sni': 1}; curl rc=28 (curl: (28) Connection timed out after 15001 milliseconds)

Evidence-derived allowlist (union of relayed hosts over 2 real runs): `registry.npmjs.org`

## Allowlist rerun: sidecar outbound_domain_allowlist = ['cdn.cypress.io', 'download.cypress.io', 'files.pythonhosted.org', 'github.com', 'install.serverless.com', 'nodejs.org', 'pypi.org', 'registry.npmjs.org', 'release-assets.githubusercontent.com', 'storage.googleapis.com']
2 of 2 real runs exited 0 with the allowlist on.

Original destination (SO_ORIGINAL_DST) visible to the Sidecar in 0 of 4 runs.

## Workload outcomes

- sidecar: 4 of 4 exited 0

## Cost (seconds per sandbox, p50 / p95, n per cell)

| phase | sidecar |
|---|---|
| sandbox create | 0.07 / 0.089 (n=2) |
| sidecar up (create + listening) | 0.82 / 0.816 (n=2) |
| first exec | 0.97 / 1.035 (n=2) |
| arm in-VM recorder | 0.29 / 0.302 (n=2) |
| workload | 1.44 / 1.701 (n=2) |
| build in-VM receipt | 0.15 / 0.188 (n=2) |
| collect sidecar log | 0.05 / 0.075 (n=2) |
| total | 3.84 / 3.93 (n=2) |

In-VM receipts declared incomplete: 0; in-VM receipt missing: 0.
