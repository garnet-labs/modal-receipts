# What the Modal VM guest kernel exposes (observed 2026-10-16)

Observed from inside a `runtime="vm"` Sandbox on Modal, kernel `7.2.9`, hypervisor
`cloud-hypervisor`, PID 1 `/__modal/runch-agent`, root with full capabilities,
cgroup v2. Source: `/proc/config.gz` (4183 lines; relevant excerpt in
`modal-vm-kernel-7.2.9.config-excerpt.txt`).

## Available today, used by this demo

| option | value | role in the receipt |
|---|---|---|
| `CONFIG_AUDIT`, `CONFIG_AUDITSYSCALL` | y | every connect/execve/clone/open-for-write syscall, with pid/ppid/comm/exe and the socket address |
| `CONFIG_PROC_EVENTS`, `CONFIG_CONNECTOR` | y | process fork/exec/exit stream (not needed; audit carries it) |
| `CONFIG_FANOTIFY`, `CONFIG_INOTIFY_USER` | y | file-event alternative (not needed) |
| `CONFIG_CGROUP_BPF`, `CONFIG_BPF_SYSCALL`, `CONFIG_BPF_JIT` | y | cgroup socket-address BPF hooks work without BTF |
| `CONFIG_NF_TABLES`, `CONFIG_NFT_LOG`, `CONFIG_NETFILTER_XT_TARGET_AUDIT` | y | per-packet accounting if ever wanted |
| `CONFIG_KEXEC`, `CONFIG_KEXEC_FILE` | y | a replacement kernel loads and executes, but the guest agent does not reconnect afterwards (tested with Ubuntu 6.8.0-147-generic; sandbox becomes unreachable) |

## Not available, which is what keeps the full Garnet recorder (Jibril, eBPF) out

| option | value | effect |
|---|---|---|
| `CONFIG_FTRACE` | not set | no tracefs, no tracepoints, no raw tracepoints |
| `CONFIG_KPROBES` | not set | no kprobes/kretprobes |
| `CONFIG_DEBUG_INFO_BTF` | not set | no `/sys/kernel/btf/vmlinux`, no CO-RE, no fentry/fexit |
| `CONFIG_BPF_EVENTS` | not set | no perf-event BPF attach |
| `CONFIG_MODULES` | not set | nothing can be loaded after boot |

Jibril v2.17.0 attaches 0 of 76 programs on this kernel and exits (observed
2026-10-02 and unchanged today).

## The one-line ask, if Modal ever wants the full recorder in the image

An opt-in guest kernel build with `CONFIG_DEBUG_INFO_BTF=y`, `CONFIG_FTRACE=y`,
`CONFIG_KPROBES=y`, `CONFIG_BPF_EVENTS=y` (and `CONFIG_FUNCTION_TRACER=y`).
Everything in this demo keeps working unchanged; the receipt gains kernel-side
process memory, file-read, and DNS-answer attribution, and loses the audit
backlog as a coverage dependency.
