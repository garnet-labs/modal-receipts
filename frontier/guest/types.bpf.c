// One tiny program per hook type Jibril uses (plus the cgroup/sock_addr, LSM and
// perf types it does not), to ask the running kernel which types it accepts.
#include <linux/bpf.h>
#include <linux/types.h>
#include <linux/ptrace.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_tracing.h>
char LICENSE[] SEC("license") = "GPL";
struct { __uint(type, BPF_MAP_TYPE_HASH); __uint(max_entries, 64); __type(key, __u32); __type(value, __u64); } counts SEC(".maps");
static __always_inline void bump(__u32 k) { __u64 *v = bpf_map_lookup_elem(&counts, &k); if (v) __sync_fetch_and_add(v, 1); else { __u64 one = 1; bpf_map_update_elem(&counts, &k, &one, BPF_ANY); } }
SEC("cgroup_skb/egress") int t_cgroup_skb(struct __sk_buff *skb) { bump(1); return 1; }
SEC("cgroup/connect4") int t_cgroup_connect4(struct bpf_sock_addr *ctx) { bump(2); return 1; }
SEC("cgroup/sock_create") int t_cgroup_sock_create(struct bpf_sock *sk) { bump(3); return 1; }
SEC("cgroup/sendmsg4") int t_cgroup_sendmsg4(struct bpf_sock_addr *ctx) { bump(4); return 1; }
SEC("sockops") int t_sockops(struct bpf_sock_ops *ops) { bump(5); return 1; }
SEC("tracepoint/syscalls/sys_enter_execve") int t_tracepoint(void *ctx) { bump(6); return 0; }
SEC("raw_tracepoint/sched_process_exec") int t_raw_tracepoint(void *ctx) { bump(7); return 0; }
SEC("kprobe/do_mmap") int t_kprobe(struct pt_regs *ctx) { bump(8); return 0; }
SEC("fentry/security_socket_connect") int BPF_PROG(t_fentry) { bump(9); return 0; }
SEC("tp_btf/sched_process_exec") int BPF_PROG(t_tp_btf) { bump(10); return 0; }
SEC("iter/task") int t_iter_task(void *ctx) { bump(11); return 0; }
SEC("lsm/socket_connect") int BPF_PROG(t_lsm) { bump(12); return 0; }
SEC("perf_event") int t_perf_event(void *ctx) { bump(13); return 0; }
SEC("uprobe") int t_uprobe(struct pt_regs *ctx) { bump(14); return 0; }
