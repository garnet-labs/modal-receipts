# Harbor rollout integrity

See [integrity-manifest.json](integrity-manifest.json) for coverage and artifact hashes.

| Trial | Verdict | Coverage incomplete |
| --- | --- | --- |
| extract-elf__Q8TvRSL | unknown | yes |
| extract-elf__tKYQDnz | unknown | yes |
| filter-js-from-html__5PmkauC | unknown | yes |
| filter-js-from-html__w8GeMcu | unknown | yes |
| mteb-leaderboard__7E6cwgb | observed | yes |
| mteb-leaderboard__VC9YNfE | observed | yes |
| mteb-retrieve__S6pS3q7 | observed | yes |
| mteb-retrieve__fwEJ75H | observed | yes |

- Guest root can alter or erase guest evidence; the sidecar is an independent SNI observer, not a kernel trace.
- Flags are observations, not findings of intent, correctness, or cheating.
- Not observed within scope is not proof of absence. Unknown is not clean.
- Hashes cover host-retained bytes. This manifest is not signed and does not prove source integrity.
