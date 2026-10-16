# Draft note (Farrukh's voice; numbers from samples/sidecar/)

Subject: built this on your Sandbox Sidecars

Erik — congrats on the $1B.

I built something small on the Sidecars you shipped this week: every VM Sandbox run gets a
receipt, recorded from a Sidecar the code in the sandbox cannot touch. Four lines around
`Sandbox.create` (the `proxy_traffic_via_sidecar` option plus one Sidecar named `garnet`); the
Sidecar reads the SNI off each relayed connection, passes the bytes through, decrypts nothing,
and the run comes back with: every HTTPS host it reached, which process chain made each
connection (optional in-VM half), whether the two records agree, and what the record does not
cover (DNS, other ports).

30 real installs from the top of npm and PyPI, nothing constructed: 24 reached only their
registry; puppeteer, cypress, sqlite3, canvas, node-sass and serverless reached seven other hosts
from postinstall scripts (`bash > node > sh > node`). The union of those hosts went straight into
the Sidecar's `outbound_domain_allowlist` and the same installs passed with it on, 10 of 10; the
one constructed step to a host outside the list was refused by your SNI match and the receipt
shows the attempt. That is the allowlist nobody knew how to write, derived from the runs.

Numbers your team will ask: Sidecar up in 0.74 s p50 / 1.13 s p95 (n=30), about 1 ms per
connection at the median through the relay (1200 requests per cell), create and first exec
unchanged. The in-VM half is optional and costs ~0.6 s per sandbox.

You see all of this host-side already; this is what the customer gets to keep, in the same format
as their GitHub Actions runs. Zero engineering to try, one runtime flag to ship.

Script and every output: https://github.com/garnet-labs/modal-receipts. `modal run sidecar_receipts.py --n 10` in your account.

Who on your team owns Sandbox Sidecars?

— Farrukh

---
Checks before sending: no "detect/threat/monitor/malicious"; no customer mention; no deck, no
partnership ask; the one constructed case is labelled; coverage stated; numbers copied from
samples/sidecar/*/SUMMARY.md; never claims to see more than Modal does host-side.
