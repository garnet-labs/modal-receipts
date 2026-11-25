# Harbor rollout integrity

See [integrity-manifest.json](integrity-manifest.json) for coverage and artifact hashes.

| Trial | Verdict | Coverage incomplete |
| --- | --- | --- |
| log-summary-date-ranges__ghuT9mW | observed | yes |
| log-summary-date-ranges__kdPXq7s | observed | yes |
| log-summary-date-ranges__mCTNMDy | unknown | yes |
| regex-log__A6UiJDP | observed | yes |
| regex-log__S9YNYVz | observed | yes |
| regex-log__gZNjk2W | observed | yes |

- Guest root can alter or erase guest evidence; the sidecar is an independent SNI observer, not a kernel trace.
- Flags are observations, not findings of intent, correctness, or cheating.
- Not observed within scope is not proof of absence. Unknown is not clean.
- Hashes cover host-retained bytes. This manifest is not signed and does not prove source integrity.
