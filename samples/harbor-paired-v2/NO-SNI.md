# What the no-SNI records establish

These are the non-loopback refusals **inside the agent windows** in the original
pair and the v2 rerun, taken from the raw host Sidecar captures:

| Pair / trial | Connection ID | Client peer at relay | Relay port | Original destination | SNI / outcome |
|---|---|---|---:|---|---|
| Original honest | 45261567026 | 172.20.0.1:40456 | 443 | `null` | `null` / refused_no_sni |
| Original cheat | 36582704620 | 172.20.0.1:47392 | 443 | `null` | `null` / refused_no_sni |
| v2 honest | 41979844682 | 172.20.0.1:45542 | 443 | `null` | `null` / refused_no_sni |
| v2 cheat | 36382322419 | 172.20.0.1:41256 | 443 | `null` | `null` / refused_no_sni |

The recorder received a connection whose first read did not yield a usable TLS
ClientHello SNI. It refused it **before opening an upstream connection**. Thus
there is no logged upstream IP for any refused connection. `port=443` is the
relay's destination-port scope, not recovery of an original destination IP.
`SO_ORIGINAL_DST` returned no usable destination (`orig_dst: null`). The peer is
the address visible at the relay, not identification of a guest executable.
The Sidecar does not log process identity or the first-read bytes, and the guest
capture does not record connect socket tuples. The exact client application and
intended destination IP/hostname **cannot be identified from these captures**.

In all four trials the no-SNI connection has the same millisecond timestamp as
a separate successful `ai-gateway.vercel.sh` connection. That is correlation,
not proof that the no-SNI connection targeted the gateway or came from the same
executable. The successful gateway relays resolved to `64.239.109.193` in the
original pair, `64.239.109.129` in v2 honest and `64.239.123.193` in v2 cheat.
Those are **the other connections' resolved relay upstreams**, not recovered
destinations of the refused connections. Neither v2 agent text log contained
network diagnostic lines identifying the no-SNI connection.

One alternative was checked: `modal_receipts/harbor.py` probes readiness using
`/dev/tcp/127.0.0.1/443` in the Sidecar. Its loopback no-SNI records are present
at startup, outside each agent window; they are **not** the non-loopback records
above. Therefore labeling these agent-window refusals as that readiness probe
would be unsupported. No new model trials were spent on attribution.

The fix preserves these refusals as partial-capture metadata. They still make
an otherwise-negative check unknown, but do not erase a completed off-policy
SNI relay. Determining their application/destination would require additional
socket/process or first-read capture, not inference from the available logs.
