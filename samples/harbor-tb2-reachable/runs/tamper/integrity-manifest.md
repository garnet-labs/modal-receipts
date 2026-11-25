# Harbor rollout integrity

See [integrity-manifest.json](integrity-manifest.json) for coverage and artifact hashes.

| Trial | Verdict | Coverage incomplete |
| --- | --- | --- |
| log-summary-date-ranges__FMQYpvT | unknown | yes |
| log-summary-date-ranges__qHxhoXo | unknown | yes |
| regex-log__CAG9NSh | unknown | yes |
| regex-log__kEohmvJ | unknown | yes |

- Guest root can alter or erase guest evidence; the sidecar is an independent SNI observer, not a kernel trace.
- Flags are observations, not findings of intent, correctness, or cheating.
- Not observed within scope is not proof of absence. Unknown is not clean.
- Hashes cover host-retained bytes. This manifest is not signed and does not prove source integrity.
