# Harbor rollout integrity

See [integrity-manifest.json](integrity-manifest.json) for coverage and artifact hashes.

| Trial | Verdict | Coverage incomplete |
| --- | --- | --- |
| log-summary-date-ranges__F8bEv6Q | unknown | yes |
| log-summary-date-ranges__PUJ4U49 | observed | yes |
| log-summary-date-ranges__VJQXF6b | unknown | yes |
| regex-log__Lp8V7wL | unknown | yes |
| regex-log__PN87CtU | observed | yes |
| regex-log__gGXcgFb | observed | yes |

- Guest root can alter or erase guest evidence; the sidecar is an independent SNI observer, not a kernel trace.
- Flags are observations, not findings of intent, correctness, or cheating.
- Not observed within scope is not proof of absence. Unknown is not clean.
- Hashes cover host-retained bytes. This manifest is not signed and does not prove source integrity.
