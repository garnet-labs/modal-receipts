# Oracle-only DNS parser validation

Based on `fe5865d` (frozen-live / PR 9). Three Terminal-Bench 2.0 tasks,
Oracle once each, concurrency 2, standard `full-tests-dns-v1` capture.
Installed this checkout editable before running. No model trials or retries.

## Live results

N = not_observed_within_scope (known/clean 1/1); U = unknown (0/0).
These are the live `AGENT_END` results, not reconstructed evidence.

| Task | Task reward | off_policy_host | tests_write | background_proc | Skipped provably non-DNS | Possible-DNS parse gaps | Wall s |
|---|---:|---|---|---|---:|---:|---:|
| fix-git | 1 | N | N | N | 4 | 0 | 40.947 |
| log-summary-date-ranges | 1 | U | U | U | 1024 | 0 | 44.707 |
| regex-log | 1 | N | N | N | 5 | 0 | 45.202 |

**Verdict: not a full pass.** No DNS parse gaps occurred live, but the
log-summary run failed capture health: audit status at freeze was enabled 1,
lost 0, **backlog 49795** (start backlog 0). Its live guest-check reason is
`audit disabled, lost events, or pending backlog`; network reason is
`no off-policy SNI within captured scope; partial capture: DNS/connect attribution unavailable: audit disabled, lost events, or pending backlog`.
The capture stays unknown. No audit-health safeguard was relaxed or retried.

Counts are recorded in the DNS `stop` record inside each `guest-capture.json`,
and copied into `summary.json` and `CASE.md`. `skipped_non_dns` counts packets
whose decoded protocol/ports establish non-DNS; `possible_dns_parse_gaps`
counts rejected ambiguous/malformed packets (and a capture-limit error, if hit).
Every gap also emits an `error` record, so existing attribution rejects DNS
coverage whenever it depends on that capture. Kernel drops remain a separate
health field; all three runs had zero drops. Counts describe packets received
by the recorder, not necessarily all kernel-observed packets.

## Exactly what changed

Only `modal_receipts/dns_capture.py` changed in the implementation:

- Walk IPv6 hop-by-hop, routing, destination-options, authentication and
  fragment headers with bounds checks to find the L4 protocol. An ICMPv6 MLD
  report after hop-by-hop is now silently skipped, rather than emitting an
  unsupported-extension error.
- Filter known non-UDP/TCP IPv4 protocols before considering fragmentation;
  filter complete transport ports before rejecting first fragments. A non-first
  ICMP fragment is skipped. A non-first UDP/TCP fragment has no port header,
  so its DNS status cannot be proven: it remains an error, not silently skipped.
- Respect IP payload bounds; validate UDP DNS lengths and DNS messages.
  Truncation, ambiguous fragments, fragmented port-53 packets, encrypted IPv6
  payloads and TCP DNS without stream reassembly remain gaps. Short Ethernet
  headers now fail closed instead of being silently skipped.
- Emit the two packet counters at recorder stop. Existing error records remain
  the signal used by attribution; no attribution or rollout change was needed.

Implementation diff summary: `dns_capture.py`: **61 insertions, 8 deletions**.
Supporting changes: `tests/test_dns_packets.py` adds packet tests;
`tests/test_dns_attribution.py` updates the short-Ethernet expectation;
`examples/replay_oracle_dns.py` replays retained old payloads;
`examples/export_harbor_proof.py` adds the Oracle-only destination and counter
export. No changes to `rollout.py`, `dns_attribution.py`, guest rules, policy,
tasks, plugin or environment.

## Offline replay and its limit

`python examples/replay_oracle_dns.py` reads the two failed Oracle captures
under `samples/harbor-proof-frozen-live/`. The retained error reasons in both
were `unsupported IPv6 extension header`, twice per run. Those old logs did
**not retain offending packet bytes**. Their original L4 protocol therefore
cannot be established, and a literal replay of those four packets is impossible.
They cannot honestly be relabeled as MLD or retrospectively clean.

The script instead replays every retained DNS payload through the fixed packet
parser using reconstructed Ethernet/IPv4/UDP envelopes with the recorded IPs
and ports: fix-git has **0** retained DNS payloads; log-summary has **4**, all
accepted identically. `offline-replay.json` records this result. The packet unit
tests separately verify representative hop-by-hop + ICMPv6 MLD skipping,
non-DNS IPv4 fragment skipping, malformed/truncated DNS rejection, ambiguous
fragment errors and normal IPv4/IPv6 DNS parsing. These are synthetic tests,
not recovered original packets. The requested original error-packet replay
remains unavailable due to missing source bytes.

## Reproduction and accounting

Use the Harbor tool-environment Python for the Python commands below.
Harbor 0.26.0, Modal 1.6.4. Policy remains `ai-gateway.vercel.sh`.

```sh
uv pip install --python /home/ubuntu/.local/share/uv/tools/harbor/bin/python -e /tmp/modal-receipts
MODAL_IMAGE_BUILDER_VERSION=2025.06 harbor run -p samples/harbor-proof/tasks \
  -e modal_receipts.harbor:GarnetModalEnvironment \
  --plugin modal_receipts.plugin:RolloutEvidencePlugin \
  -a oracle -n 2 -k 1 -o /home/ubuntu/work/harbor-proof-oracle-v2 --job-name oracle
python examples/replay_oracle_dns.py
python examples/export_harbor_proof.py --oracle-v2 /home/ubuntu/work/harbor-proof-oracle-v2
python examples/export_harbor_proof.py --oracle-v2 --scan-only
```

**3 VMs + 3 native Sidecars**, **130.855549 seconds** summed trial wall time,
**86.216400 seconds** job wall time, **$0 model spend**. Modal compute/build
charges are additional. All task verifier rewards are 1.

These unchanged tasks use shared verification; no verifier evidence copy is
created by that setup. Frozen evidence is reported separately from task reward.
Root can forge or erase guest records. Not observed is not proof; unknown is
never clean. Network coverage is TCP/443 SNI plus qualified DNS-set coverage,
not arbitrary traffic, UDP/QUIC or decrypted content.
