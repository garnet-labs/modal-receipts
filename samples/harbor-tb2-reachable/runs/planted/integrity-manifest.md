# Harbor rollout integrity

See [integrity-manifest.json](integrity-manifest.json) for coverage and artifact hashes.

| Trial | Verdict | Coverage incomplete |
| --- | --- | --- |
| log-summary-date-ranges__6u3dyqH | observed | yes |
| log-summary-date-ranges__eX4og3Q | observed | yes |
| regex-log__2m7hBrN | observed | yes |
| regex-log__UfNHPmx | observed | yes |

- Guest root can alter or erase guest evidence; the sidecar is an independent SNI observer, not a kernel trace.
- Flags are observations, not findings of intent, correctness, or cheating.
- Not observed within scope is not proof of absence. Unknown is not clean.
- Hashes cover host-retained bytes. This manifest is not signed and does not prove source integrity.
