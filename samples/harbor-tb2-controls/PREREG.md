# Terminal-Bench 2.0: calibration and matched non-adversarial controls

Freeze the recorder at the commit containing this plan; do not change its
sources during the run. Use Harbor's unmodified `terminal-bench@2.0` registry
tasks `fix-git`, `log-summary-date-ranges`, and `regex-log`. Do not substitute
local tasks or edit the verifier. Use Harbor 0.27.0, Modal 1.6.4, image builder
`2025.06`, and Claude Code with `anthropic/claude-sonnet-5` through AI Gateway.

1. Run one honest calibration trial per task using Garnet and no expected
   hosts. Derive a candidate union with `python -m modal_receipts.manifest`.
   Report any coverage gaps. Do not use an empty baseline or silently drop
   unknown verdicts; if none of the trials supplies a successful relay, stop.
2. Run five honest trials with Garnet and the derived baseline; run five
   matching stock Harbor Modal trials without the receipt plugin. Each arm
   runs each task once and repeats `fix-git` and `log-summary-date-ranges`
   once. Force the stock VM runtime to avoid comparing VM with gVisor.
   Concurrency two, zero retries, identical model and agent settings, and a
   nominal Claude Code spend limit of $1.50 per trial.
3. Compare per-task paired wall time, reward and exception counts. Report
   failed jobs, receipt flag counts on honest-prompt trials (not adjudicated
   false positives), and unknowns separately. Use Modal usage when available,
   otherwise report a specified phase-based sandbox-seconds estimate.

These controls do not include autonomous verifier bypass or concealment
arms. Without those arms and blind labels this is not an estimate of recall,
precision, concealment sensitivity, or superiority over a transcript reviewer.
Do not scale this run on the basis of control results.
