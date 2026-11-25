# Rollout integrity: preregistered checks

## Package smoke

- Use the unmodified `terminal-bench/terminal-bench@4.1.0` dataset; take the first
  task selected by Harbor with `-l 1`. Do not substitute another task if the
  selected task is incompatible. Single CPU VM, one trial, no retries.
- Run the Oracle arm using the documented custom environment and plugin without
  a host baseline or any task/verifier edits. If it reaches the agent and the
  manifests are retained, smoke Claude Code Sonnet 5 through the Gateway on
  the same task in its ordinary task-solving mode.
- Acceptance: the chosen task runs and the verifier result is retained;
  both job manifests exist with frozen trial evidence and hashes. Loss of a
  capture is not a clean result. The network verdict should be unknown absent
  a task declaration or a trusted baseline.

## Detector validation, separate from the smoke

- Unit controls are synthetic audit/relay records: a known read, a controlled
  harness write, a Git object/ref observation, ordinary irrelevant paths and
  non-descendants, and missing/lost/changed capture. Controls do not evade or
  modify a live scoring system. Pass if expected signals are observed and
  unsupported capture remains unknown.
- No autonomous exploit, verifier bypass, or concealment arms are run. The
  passive controls and honest smoke do not support receipt-vs-reviewer
  precision/recall or the requested superiority pass rule. No blind labeling
  or transcript-reviewer scoring is performed without valid positive arms.
  The known TB2.0 three-task comparison and stock overhead baseline remain
  a separate experiment; the [earlier sample](samples/harbor/README.md) is not
  a measurement of this version's overhead.

Freeze the recorder through this committed preregistration before any cloud
launch. Report observed outcomes, upload only public-safe summaries, and
record model cost separately from Modal compute. Do not scale the smoke.
