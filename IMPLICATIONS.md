# Implications: from the in-VM approach to the Sidecar integration (2026-10-16)

Facts are from today's runs (`samples/sidecar/`) and Modal's Sidecar docs; anything else is marked
(inference) or ASSUMPTION. Language rules for partner-facing material apply throughout.

## 1. What changed between the two approaches

| | in-VM recorder (yesterday) | Sidecar recorder (today) |
|---|---|---|
| where the record lives | inside the sandbox; root in the sandbox can edit it | a separate container the sandbox cannot create, stop or edit |
| what it needs from the customer | `auditd` + scripts in their image, `resolv.conf` rewritten | 4 lines around `Sandbox.create`; the image is untouched |
| what it records | every connect/execve/clone (+ files) with process chains | every TCP/443 host by SNI, bytes, timing; no process |
| coverage statement | from the kernel's own audit counters | from Modal's relay semantics (TCP/443 only) |
| cost | arm 0.35 s + receipt 0.27 s; file rule opt-in | Sidecar up 0.74 s once; ~1 ms per connection |
| who could ship it | the customer, per image | Modal, as a runtime option; or the customer, today |
| production shape | cgroup-BPF + proc connector (Modal-side work) | the same Sidecar, as a platform flag |

The two are now layered rather than alternatives: the Sidecar is the independent record and the
default; the in-VM half is optional and exists for process attribution and the agreement check.

## 2. Integration implications

- **Install surface shrinks to zero.** No change to the customer's image, no daemon in the sandbox,
  no `resolv.conf` edit. That removes the objections "we won't put auditd in customer images" and
  "your DNS trick breaks pinned resolvers" entirely for the default path.
- **The receipt is now cross-container.** The driver must merge two records with different clocks
  and windows. Done by windowing the comparison on the in-VM capture window; connections outside it
  are counted, not compared. Any integration (Modal's or ours) must do the same or will produce false
  "incomplete" verdicts (we hit this on the first probe run).
- **Fail-closed changes start-up ordering.** HTTPS from the sandbox is refused until the Sidecar
  listens (0.74 s p50). A customer who starts their workload immediately after `create` will see
  the first connection refused unless they wait on the Sidecar (the driver polls :443). An
  integration should start the Sidecar in parallel with `create` and expose readiness; in a
  platform flag Modal would do this inside the runtime.
- **Memory is reserved, not shared.** `vm_sidecar_memory_reserve_mib` (>= 1024 for the main
  container to stay above) plus `experimental_memory_reserve_consume_mib`. The Sidecar's own RSS
  is small (asyncio Python, ASSUMPTION ~30 MB; not measured today), but the reservation is what the
  customer pays for. A platform flag could size it at tens of MB.
- **One Sidecar name per Sandbox, policy fixed at creation.** A Sidecar's allowlist cannot be
  updated; replace the Sidecar to change it (Modal docs). Evidence-derived allowlists therefore
  roll forward between runs, not within one.
- **Coverage is TCP/443 only unless the main container is also fenced.** With
  `outbound_cidr_allowlist=[]` on the main container (allowed next to the relay; tested for port
  80), everything the platform lets out except DNS goes through the Sidecar. That is the shape to
  recommend when a customer wants a receipt that is complete for permitted egress; without it, the
  receipt must (and does) say that other ports are not covered.
- **No original destination.** `SO_ORIGINAL_DST` is not forwarded (64/64 runs, and documented).
  Hosts are SNI; a client that pins an IP with a different SNI is recorded under the SNI, the same
  limit Modal's own allowlist has. TLS without SNI is a policy decision (we refuse and record).
- **gVisor sandboxes are not covered by this lane.** Sidecars with the relay were exercised on
  `runtime="vm"` only. ASSUMPTION: the relay works the same on the default runtime; not run today.

## 3. Usage implications (who turns it on and why)

- **Agent platforms on Modal** (coding agents, RL rollouts): one receipt per run with the host list
  and the process chain is the per-run statement a grader or reviewer reads; the comparison across
  runs ("24 same, 6 new, here is the process") is what they act on. Today's cohort shows the shape
  with real installs; the SWE-bench lane from yesterday (0 hosts per rollout, writes confined to
  `/testbed`) is the RL version and should be rerun with the Sidecar for the side-by-side.
- **Allowlist authoring becomes mechanical.** Customers who switch on `outbound_domain_allowlist`
  today break on exactly the postinstall fetchers in the cohort and have no list. Union of relayed
  hosts over n runs -> allowlist -> rerun passes (10/10) is the loop; the receipt shows a refused
  host as an attempt with 0 bytes back rather than a silent failure.
- **The agreement check is only as strong as the in-VM record is present.** Without the optional
  half the receipt has hosts but no process and no agreement; the verdict field should then say
  `no_in_vm_record` rather than imply anything. (Driver behaviour today: the in-VM half is on in the
  sidecar cell; the "sidecar only" mode is the next knob to add.)
- **Reviewer/grader consumption** follows the locked layered model: receipt -> gate -> MCP pull ->
  adapters. The Modal receipt already carries the coverage block the GitHub Actions public profile
  lacks; closing that gap on the Garnet side is a prerequisite for "receipts as verifiers".

## 4. Commercial implications

- **The capture is a commodity; say so.** Logging SNI from a Sidecar is a weekend for Modal or
  Ramp. What is not: process attribution, the agreement check, cross-run comparison, the same
  receipt from GitHub Actions / Modal / K8s, and reviewers reading it through MCP. The demo now
  shows four of those five on real runs; the cross-substrate side-by-side (same package, same
  schema, GitHub Actions + Modal) is the remaining must-have from the adversarial review.
- **The pitch line holds literally now:** zero engineering to try (customer, today, four lines);
  one runtime flag to ship (Modal, same Sidecar as a platform option). Yesterday the first half
  was false for the product.
- **Pricing shape (inference):** per-run receipt fits Modal's per-second billing; the customer's
  marginal cost is the Sidecar reservation and ~0.75 s. Garnet's value is in the receipt format,
  comparison and consumption surface, which argues for pricing per recorded run or per workspace
  rather than per byte relayed.
- **Channel (inference):** Modal engagement becomes pull-driven if an agent platform running on
  Modal turns receipts on; the note to Erik asks for the Sidecar owner, the concrete follow-up is
  "we supply the Sidecar image and schema as a runtime flag; you keep the data".
- **Risk:** Sidecars are beta (`_experimental_sidecars`, `proxy_traffic_via_sidecar`). API shape and
  semantics may change; the recorder depends on exactly two documented behaviours (raw TCP on :443,
  fail-closed). Keep the integration to those two, and keep the in-VM path as the fallback that
  needs nothing from Modal.

## 5. Modal's likely preferences, and how the design answers them (inference unless cited)

- **Architecture: platform-side, not image-side.** Modal built Sidecars precisely so auxiliary
  processes live outside the customer's image; a recorder as a Sidecar matches their model, a
  recorder in the image contradicts it. The runtime-flag version is the same Sidecar started by
  the runtime, no new primitive required.
- **Performance: sub-second start is the brand.** Measured: create and first exec unchanged;
  Sidecar up 0.74 s p50 (overlappable); per connection ~1 ms at the median, p95 within noise at
  n=1200. The one thing to improve before a flag is tail behaviour under many concurrent flows
  (the asyncio relay is single-process; not stressed beyond 17 concurrent connections today).
- **Security posture (their word for it; we do not use it in partner copy):** nothing decrypted,
  no CA installed in the sandbox, no inspection of payload; the Sidecar is one more container
  under their existing isolation; `outbound_domain_allowlist` enforcement stays theirs and is
  matched on SNI exactly as documented. The demo deliberately does not terminate TLS (their
  mitmproxy example does, for request filtering); Garnet's position is that the receipt should
  never require it.
- **Reliability: fail-closed is already their choice** ("HTTPS connections are refused instead of
  going out directly"). A recorder in the relay path means a recorder crash refuses egress. Today's
  recorder isolates per-connection exceptions (first probe failure was a parser exception that took
  every connection with it; fixed and now logged per flow). For a platform flag the relay should
  have a documented behaviour on recorder failure (refuse vs pass-through-unrecorded, with the
  receipt saying which), and a readiness signal.
- **Operational preferences (inference):** they will want the Sidecar image pinned and small
  (debian_slim py3.12 today), no outbound traffic of its own beyond the relayed flows, logs
  retrievable without exec (a Volume or stdout), and no per-customer configuration beyond the
  allowlist. All four are small changes to `recorder.py`.
- **What they will push back on:** anything that reads like "we see what you cannot" (we never
  claim it), per-byte inspection, and a receipt that implies completeness it does not have. The
  coverage line on every receipt is the answer to the third.

## 6. Open decisions (for Farrukh)

1. Default shape to recommend: Sidecar only (hosts, no process) vs Sidecar + optional in-VM half.
   Today's artifacts measure the second; the first needs the `no_in_vm_record` verdict added.
2. Whether to pair the relay with `outbound_cidr_allowlist=[]` on the main container in the
   recommended four lines (coverage becomes "all permitted egress except DNS"; tested for port 80
   only).
3. TLS without SNI: refuse and record (today) vs relay unnamed and record as unnamed.
4. Cross-substrate side-by-side (GitHub Actions + Modal, same package) before the note goes out,
   per the adversarial review; this lane did not produce it.
5. Whether the SWE-bench rollouts (yesterday's lane) are rerun with the Sidecar for the RL audience.
