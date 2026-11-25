# What rollout evidence tells us on CPU Modal VMs

**The pilot showed that we can collect scoped evidence during an agent run. It did not show that the observer catches model-authored reward hacking or beats a transcript reviewer.** A separate scripted experiment produced known signals; the prompt-only pilot did not produce a scorable comparison. [Scripted experiment][scripted] · [Prompt-only pilot][pilot]

## What the pilot found

The prompt-only pilot ran two Terminal-Bench 2.0 tasks, `regex-log` and `log-summary-date-ranges`, six times per arm. Reward is the benchmark score, not an integrity verdict. [Trial results][trials]

| Prompt-only arm | Reward 1 | Labeled successful bypasses | Transcript reviewer flags | Frozen integrity verdicts |
|---|---:|---:|---:|---:|
| Reward pressure | 6/6 | 0/6 | 0/6 | 0/6 |
| Reward pressure and concealment | 6/6 | 0/6 | 0/6 | 0/6 |

Sources: [trial results][trials], [blind labels][labels], and [reviewer output][reviewer]. The labels were made before opening receipts, but from transcripts only; no independent final filesystem diff was available. [Labeling method][labeling]

Two design failures made the result unscorable:

1. **The grader was not available while the agent ran.** All six reward-pressure runs looked for the tests without finding the grader. Harbor loaded it after the agent phase on these tasks. All six concealment-arm transcripts recorded refusals, so they did not test concealment after a successful bypass. [Pilot evidence][labeling]
2. **The integrity plugin hooks did not run.** The custom environment still wrote 12 stop-time network receipts. These report TLS hostnames for the sandbox lifecycle, not a frozen, agent-phase integrity verdict. The archive lacks the original launch command, but the artifact pattern and separate capture paths show why stop-time receipts alone are insufficient. [Artifact comparison][wiring] · [Plugin implementation][plugin]

With no positive labels, recall is undefined for both approaches. With no reviewer flags, reviewer precision is undefined too. The missing observer verdicts also prevent measuring its precision or comparing it with the reviewer. None of these gaps is a zero error rate. [Archived result and pass rule][pilot]

## What we can claim

- **Known signals were visible in a separate scripted experiment.** Three deliberately scripted cases registered on the network, test-write, and background-process checks; none of nine Oracle or honest controls registered on those three checks. That is evidence about the specified signals, not 100% accuracy, model intent, or superiority to a reviewer. [Scripted results and limitations][scripted]
- **The standard observer produced frozen artifacts in a separate smoke test.** It preserved scoped results even after a model run exited at its turn limit. Git and network-policy checks could still be unknown; writing a manifest did not make the capture complete. [Smoke results][smoke]
- **Routine Git work can trigger the detector.** Two of five honest-prompt observer trials flagged Git-object reads, both on a Git repair task; the other three lacked a Git-object watch. These were not independently adjudicated false positives. Treat generic object reads as diagnostics, not evidence of cheating. [Honest controls][controls]

## Coverage and limitations

- **CPU Modal VMs only.** The observed setup combines Linux audit inside the guest with a separate Sidecar for network metadata. It does not use Jibril or eBPF, and this report makes no GPU parity claim. [Tested setup][scope] · [Kernel compatibility measurements][kernel]
- **Network coverage is bounded.** The Sidecar sees TLS ClientHello hostnames (SNI) on TCP port 443, not decrypted traffic. The agent-phase plugin can use qualified DNS and connect evidence for some connections where no hostname was visible; that is not unique socket-to-host attribution. This is not general DNS monitoring and does not cover QUIC, other ports, or the Sidecar’s own traffic. [Network scope and DNS limits][dns]
- **The receipt is not root-proof.** Guest root can alter guest audit and DNS evidence. The Sidecar is a separate source, not an attestation of guest state. Manifests list artifacts and hashes, but are unsigned; an unknown check is not a clean result, and no observation within scope does not prove absence. [Manifest and scope][scope] · [Smoke limitations][smoke]

## What a credible next measurement would require

First verify that an explicit plugin opt-in produces a frozen verdict on **every** experiment job, not just a stop-time receipt. A harmless, labeled event against a dummy fixture can be a positive control for signal collection; a deliberately incomplete **synthetic record** can test the unknown path without modifying live evidence. Keep matched honest controls. Freeze labels based on trajectories and final state before opening receipts, and give the comparison reviewer transcripts only, without labels or receipts. Report synthetic detection separately from any claim about model-authored cheating, and report undefined metrics as undefined. These are proposed checks, not a completed rerun. [Why the original setup was unscorable][wiring] · [Positive and missing-evidence regression tests][tests] · [Prior comparison protocol][plan]

[scripted]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/samples/harbor-proof-combined-live/README.md#live-results-and-verdict
[pilot]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/samples/harbor-tb2-adversarial/README.md
[trials]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/samples/harbor-tb2-adversarial/README.md#per-trial-results-and-sidecar-comparison
[labels]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/samples/harbor-tb2-adversarial/labels.json
[reviewer]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/samples/harbor-tb2-adversarial/reviewer.json
[labeling]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/samples/harbor-tb2-adversarial/README.md#recorded-prompts-and-labels
[wiring]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/samples/harbor-tb2-adversarial/README.md#why-only-stop-time-receipts-exist
[plugin]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/modal_receipts/plugin.py
[smoke]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/samples/harbor-rollout-integrity-smoke/README.md
[controls]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/samples/harbor-tb2-controls/README.md#coverage-and-flags
[scope]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/README.md#harbor-terminal-bench-on-modal
[kernel]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/kernel/README.md
[dns]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/README.md#dns-set-coverage-for-no-sni-refusals
[tests]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/tests/test_rollout.py
[plan]: https://github.com/garnet-labs/modal-receipts/blob/d79204ec463fdf7aa8a569795a919d188b7abf19/samples/harbor-tb2-controls/PREREG.md
