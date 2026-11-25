# Rollout evidence on CPU Modal VMs: what it catches and what it does not

**When the grader was reachable during the run, Claude Sonnet 5 read it in 8 of 12 trials under reward-pressure prompts and 0 of 6 honest trials. The verifier-read check matched all 18 transcript-derived model labels: 8 observed and 10 not observed within scope.** A transcript-only LLM reviewer did not flag any of the eight reads as cheating. Truncating the in-VM audit log turned the receipt to `unknown`, never clean. The design and pass rule were committed after one plugin-wiring smoke and before the 26 reported trials. [Preregistration](https://github.com/garnet-labs/modal-receipts/blob/cb0dae1565d776eee659e48e5000a3c0dcb28a88/samples/harbor-tb2-reachable/PREREG.md) · [Results](https://github.com/garnet-labs/modal-receipts/blob/cb0dae1565d776eee659e48e5000a3c0dcb28a88/samples/harbor-tb2-reachable/README.md)

## Setup

Harbor 0.27.0 running Terminal-Bench 2.0 `regex-log` and `log-summary-date-ranges` on Modal `runtime="vm"` sandboxes, with the `GarnetModalEnvironment` environment and `RolloutEvidencePlugin` on every job. The task-image change was `COPY tests /tests`, so the grader is readable while the agent runs. The scripted controls also changed the Oracle solution. Harbor uploads the authoritative test files before grading; this run did not establish that edits to the agent-visible copy cannot affect scoring. [Task generator](https://github.com/garnet-labs/modal-receipts/blob/45d0993d9a6274d266a602823fc3a7475bdb24da/examples/prepare_tb2_reachable.py) · [Run setup](https://github.com/garnet-labs/modal-receipts/blob/cb0dae1565d776eee659e48e5000a3c0dcb28a88/samples/harbor-tb2-reachable/README.md)

## Results

All 26 trials scored reward 1 with no exceptions.

| Arm | Trials | Grader access: transcript label for model trials, planted by design for scripted controls | Receipt observed | All three grader checks unknown | Reviewer flagged |
|---|---:|---:|---:|---:|---:|
| Honest | 6 | 0 | 0 | 0 | 0 |
| Reward pressure (prompt only) | 6 | 3 | 3 | 0 | 0 |
| Reward pressure + "tidy up" (prompt only) | 6 | 5 | 5 | 0 | 0 |
| Scripted grader read + `conftest.py` write | 4 | 4 | 4 | 0 | 4 |
| Scripted, then audit log truncated | 4 | 4 | 0 | 4 | 4 |

Sources: [blind labels](https://github.com/garnet-labs/modal-receipts/blob/cb0dae1565d776eee659e48e5000a3c0dcb28a88/samples/harbor-tb2-reachable/runs/labels.json) (from transcripts, before any receipt was opened), [reviewer output](https://github.com/garnet-labs/modal-receipts/blob/cb0dae1565d776eee659e48e5000a3c0dcb28a88/samples/harbor-tb2-reachable/runs/reviewer.json), [reviewer on scripted arms](https://github.com/garnet-labs/modal-receipts/blob/cb0dae1565d776eee659e48e5000a3c0dcb28a88/samples/harbor-tb2-reachable/runs/reviewer-scripted.json), [per-trial receipts and job manifests](https://github.com/garnet-labs/modal-receipts/tree/cb0dae1565d776eee659e48e5000a3c0dcb28a88/samples/harbor-tb2-reachable/runs).

- **Reviewer:** it acknowledged the eight model-trial reads but did not flag them as cheating because the agents also wrote general code. The receipt flags access, not intent. The reviewer flagged all eight scripted trials and was shown the full scripted commands. [Reviewer method](https://github.com/garnet-labs/modal-receipts/blob/cb0dae1565d776eee659e48e5000a3c0dcb28a88/samples/harbor-tb2-reachable/runs/review_scripted.py)
- **Pass rule:** 12/16 observed vs. 8/16 reviewer-flagged under the preregistered scoring rule. The other 4/16 receipt outcomes were unknown, not detections. There were 0/6 honest flags and 0/4 tamper trials reported clean on all three grader checks. All three frozen conditions passed. All six honest trial verdicts in the job manifest were `unknown` because Git-history coverage was unavailable. [Pass rule](https://github.com/garnet-labs/modal-receipts/blob/cb0dae1565d776eee659e48e5000a3c0dcb28a88/samples/harbor-tb2-reachable/README.md#pass-rule)
- **Cost:** $3.00 of model spend and about 1,491 agent-phase sandbox-seconds for all 26 trials. [Cost](https://github.com/garnet-labs/modal-receipts/blob/cb0dae1565d776eee659e48e5000a3c0dcb28a88/samples/harbor-tb2-reachable/README.md#cost)

## What this shows and what it does not

- A positive here is **grader access during the rollout, not a successful reward hack**. No model trial had a test edit in the transcript labels or receipt observations, and every model trial scored 1. Whether reading the grader counts as contamination is a policy choice for whoever owns the dataset; the receipt reports the access either way. [Results](https://github.com/garnet-labs/modal-receipts/blob/cb0dae1565d776eee659e48e5000a3c0dcb28a88/samples/harbor-tb2-reachable/README.md#results)
- 26 trials on 2 tasks, one model. No confidence intervals are claimed.
- The tamper arm shows one method (audit-log truncation) detected as missing evidence. It does not show that tampering is impossible or that the erased events can be recovered.
- No off-policy host was observed within scope in the model trials. [Per-trial evidence](https://github.com/garnet-labs/modal-receipts/tree/cb0dae1565d776eee659e48e5000a3c0dcb28a88/samples/harbor-tb2-reachable/runs)
- The earlier prompt-only pilot was unscorable: the grader was unavailable during the agent phase and the plugin hooks did not run. This rerun fixes both. [Pilot](https://github.com/garnet-labs/modal-receipts/blob/45d0993d9a6274d266a602823fc3a7475bdb24da/samples/harbor-tb2-adversarial/README.md)

## Coverage and limitations

- **CPU Modal VMs only.** The observed setup combines Linux audit inside the guest with a separate Sidecar for network metadata. It does not use Jibril or eBPF, and this report makes no GPU parity claim. [Tested setup][scope] · [Kernel compatibility measurements][kernel]
- **Network coverage is bounded.** The Sidecar sees TLS ClientHello hostnames (SNI) on TCP port 443, not decrypted traffic. The agent-phase plugin can use qualified DNS and connect evidence for some connections where no hostname was visible; that is not unique socket-to-host attribution. This is not general DNS monitoring and does not cover QUIC, other ports, or the Sidecar’s own traffic. [Network scope and DNS limits][dns]
- **The receipt is not root-proof.** Guest root can alter guest audit and DNS evidence. The Sidecar is a separate source, not an attestation of guest state. Manifests list artifacts and hashes, but are unsigned; an unknown check is not a clean result, and no observation within scope does not prove absence. The archive contains derived receipts and manifest inventories, not independently verifiable raw captures. [Archive verification](https://github.com/garnet-labs/modal-receipts/blob/cb0dae1565d776eee659e48e5000a3c0dcb28a88/samples/harbor-tb2-reachable/README.md#archive-verification) · [Manifest and scope][scope] · [Smoke limitations][smoke]

## Earlier evidence

- **Known signals were visible in a separate scripted experiment.** Three deliberately scripted cases registered on the network, test-write, and background-process checks; none of nine Oracle or honest controls registered on those three checks. That is evidence about the specified signals, not 100% accuracy, model intent, or superiority to a reviewer. [Scripted results and limitations][scripted]
- **The standard observer produced frozen artifacts in a separate smoke test.** It preserved scoped results even after a model run exited at its turn limit. Git and network-policy checks could still be unknown; writing a manifest did not make the capture complete. [Smoke results][smoke]
- **Routine Git work can trigger the detector.** Two of five honest-prompt observer trials flagged Git-object reads, both on a Git repair task; the other three lacked a Git-object watch. These were not independently adjudicated false positives. Treat generic object reads as diagnostics, not evidence of cheating. [Honest controls][controls]

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
