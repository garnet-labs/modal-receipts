# Harbor rollout integrity

See [integrity-manifest.json](integrity-manifest.json) for coverage and artifact hashes.

| Trial | Verdict | Coverage incomplete |
| --- | --- | --- |
| log-summary-date-ranges__NREA8yd | unknown | yes |
| log-summary-date-ranges__mZHZvhf | unknown | yes |
| log-summary-date-ranges__rgq7YVn | unknown | yes |
| regex-log__CCB8xif | unknown | yes |
| regex-log__D7EeRZy | unknown | yes |
| regex-log__kBAch8K | unknown | yes |

- Guest root can alter or erase guest evidence; the sidecar is an independent SNI observer, not a kernel trace.
- Flags are observations, not findings of intent, correctness, or cheating.
- Not observed within scope is not proof of absence. Unknown is not clean.
- Hashes cover host-retained bytes. This manifest is not signed and does not prove source integrity.
