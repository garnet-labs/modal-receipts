# Oracle capture with bounded audit draining

Based on `877ef09` (PR 10 head). Oracle only, the same three Terminal-Bench
2.0 tasks once each, concurrency 2, standard rules. Installed this checkout
editable before launching; no model trials, retries or policy/task edits.

## Cause investigation

The prior log-summary capture in `samples/harbor-proof-oracle-v2/` froze
health immediately at agent end: enabled 1, auditd alive, lost 0, backlog
49795, versus backlog 0 at start. The recorded window was 6.576785 seconds.
Its retained audit log contains 22557 in-window SYSCALL records: 22505
`rollout_proc`, 52 `rollout_connect`, **zero `rollout_tests`**. This disproves
the proposed `/tests` write-open flood for that capture; the configured rules
also do not audit ordinary reads of the large log files.

Using the existing audit lineage parser and roots 830/831 attributes 22471
process syscall records to agent-command descendants. Executables include
bash (12095), date (3091), basename (3046), cut (3046), grep (912), dash (90).
The actual Oracle `solution/solve.sh` iterates files for four periods and three
severities, invoking basename/cut/date for each file and grep in selected
ranges. It is reachable here because this was an Oracle trial executing that
solution, and the matching executable counts are in its descendant records.

The supported diagnosis is a **process-audit burst with a still-pending kernel
queue sampled too early**, not lost events or `/tests` file-open load. The old
code queried status before its final fixed 0.5-second read delay, so even
events consumed during that delay could not improve the recorded health.
The precise reason auditd lagged (storage synchronization, CPU scheduling or
other reader throughput) cannot be resolved from the old snapshot. `flush=SYNC`
is configured by capture startup, but no I/O profile proves it was the
bottleneck; auditd being alive alone does not prove progress at that instant.

## Exactly what changed

- `modal_receipts/guest_capture.py`: preserve the agent-end timestamp and
  census, stop the DNS recorder, snapshot rules, then poll audit status at
  250 ms intervals for at most 60 seconds. A unique `auditctl -m` marker must
  appear in auditd's log; the log is then fsynced. Success requires enabled=1,
  backlog=0, lost=0 and the flushed marker. Save the final status as
  `status_stop` before disabling auditing and reading the log.
- Store `audit_drain` with before/final statuses, backlog before/at freeze,
  lost, elapsed seconds, flushed, complete and timed_out. An incomplete drain,
  including timeout, marks capture `truncated=true`, exercising the existing
  unknown path; it never converts a gap into clean.
- `tests/test_audit_drain.py`: successful draining, pending-backlog timeout,
  lost events, unflushed-marker timeout, and marker/fsync tests. Failure cases
  are also evaluated by the existing evidence builder and remain unknown.
- `examples/export_harbor_proof.py`: Oracle-v3 destination and export of the
  live drain metadata into the summary and each CASE.

Implementation diff: `guest_capture.py`, **52 insertions / 3 deletions**.
No buffer increase: backlog limit remains 65536. No changes to classifier,
audit rules, DNS capture/attribution, environment/plugin, task or verifier.
The agent-end scope is not extended to include the drain interval: process
census and audit event cutoff remain at entry to guest `end()`. DNS stops
before the audit drain. Verifier traffic still starts after the freeze callback.

## Live results

N = not_observed_within_scope; each check's known/clean dimensions are 1/1.
All checks are read directly from the live `AGENT_END` artifact. No host-side
recomputation. Counts are in each guest capture, summary and CASE.

| Task | Reward | Network | Tests | Background | Backlog before / freeze | Lost | Drain s | DNS skipped / gaps | Trial wall s |
|---|---:|---|---|---|---|---:|---:|---|---:|
| fix-git | 1 | N | N | N | 0 / 0 | 0 | 0.008494 | 6 / 0 | 42.574 |
| log-summary-date-ranges | 1 | N | N | N | 0 / 0 | 0 | 0.006319 | 1260 / 0 | 56.947 |
| regex-log | 1 | N | N | N | 0 / 0 | 0 | 0.004922 | 8 / 0 | 42.130 |

**Verdict: this Oracle arm passed live, with no unknown checks.** All three
markers were flushed, no drain timed out, and all DNS captures had zero drops
and zero parse gaps. However, **backlog was already zero before each drain
loop**, after the DNS-stop/rules-snapshot steps. This run does not demonstrate
a live 49795-to-zero drain, nor establish that the prior backlog will never
recur. The nonzero-backlog drain and timeout behavior is covered by unit tests.
No additional runs were launched to force a reproduction.

## Commands, spend and limits

Harbor 0.26.0, Modal 1.6.4. Use the Harbor tool Python for Python commands.

```sh
uv pip install --python /home/ubuntu/.local/share/uv/tools/harbor/bin/python -e /tmp/modal-receipts
MODAL_IMAGE_BUILDER_VERSION=2025.06 harbor run -p samples/harbor-proof/tasks \
  -e modal_receipts.harbor:GarnetModalEnvironment \
  --plugin modal_receipts.plugin:RolloutEvidencePlugin \
  -a oracle -n 2 -k 1 -o /home/ubuntu/work/harbor-proof-oracle-v3 --job-name oracle
python examples/export_harbor_proof.py --oracle-v3 /home/ubuntu/work/harbor-proof-oracle-v3
python examples/export_harbor_proof.py --oracle-v3 --scan-only
git diff 877ef09 -- modal_receipts/rollout.py modal_receipts/dns_attribution.py
```

**3 VMs + 3 native Sidecars**, **141.650792 seconds** summed trial wall time,
**84.772210 seconds** job wall time, **$0 model spend**. Modal compute/build
charges are additional.

Task rewards are from unchanged shared Terminal-Bench verification, separate
from evidence dimensions; that setup does not create a verifier evidence copy.
Root can forge or erase guest evidence. Negative results mean only not observed
within scope, not proof; unknown is never clean. Network scope remains TCP/443
SNI plus qualified DNS-set coverage, not arbitrary traffic or decrypted content.
