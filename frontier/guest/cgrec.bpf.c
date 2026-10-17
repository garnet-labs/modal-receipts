// cgroup-BPF-only recorder: connect4/6, sendmsg4/6, sock_create with pid/comm.
// No CO-RE, no kernel BTF needed.
#include <linux/bpf.h>
#include <linux/types.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>
char LICENSE[] SEC("license") = "GPL";
struct ev { __u64 ts; __u32 pid; __u32 tgid; __u32 kind; __u32 family; __u32 type; __u32 proto; __u32 addr[4]; __u16 port; char comm[16]; };
struct { __uint(type, BPF_MAP_TYPE_RINGBUF); __uint(max_entries, 1 << 20); } events SEC(".maps");
static __always_inline void emit_addr(struct bpf_sock_addr *ctx, __u32 kind, int v6) {
    struct ev *e = bpf_ringbuf_reserve(&events, sizeof *e, 0); if (!e) return;
    __u64 id = bpf_get_current_pid_tgid();
    e->ts = bpf_ktime_get_ns(); e->pid = (__u32)id; e->tgid = id >> 32; e->kind = kind;
    e->family = ctx->user_family; e->type = ctx->type; e->proto = ctx->protocol;
    e->addr[0] = 0; e->addr[1] = 0; e->addr[2] = 0; e->addr[3] = 0;
    if (!v6) e->addr[0] = ctx->user_ip4;
    else { e->addr[0] = ctx->user_ip6[0]; e->addr[1] = ctx->user_ip6[1]; e->addr[2] = ctx->user_ip6[2]; e->addr[3] = ctx->user_ip6[3]; }
    e->port = bpf_ntohs(ctx->user_port);
    bpf_get_current_comm(e->comm, sizeof e->comm);
    bpf_ringbuf_submit(e, 0);
}
SEC("cgroup/connect4") int rec_connect4(struct bpf_sock_addr *ctx) { emit_addr(ctx, 1, 0); return 1; }
SEC("cgroup/connect6") int rec_connect6(struct bpf_sock_addr *ctx) { emit_addr(ctx, 1, 1); return 1; }
SEC("cgroup/sendmsg4") int rec_sendmsg4(struct bpf_sock_addr *ctx) { emit_addr(ctx, 2, 0); return 1; }
SEC("cgroup/sendmsg6") int rec_sendmsg6(struct bpf_sock_addr *ctx) { emit_addr(ctx, 2, 1); return 1; }
SEC("cgroup/sock_create") int rec_sock_create(struct bpf_sock *sk) {
    struct ev *e = bpf_ringbuf_reserve(&events, sizeof *e, 0); if (!e) return 1;
    __u64 id = bpf_get_current_pid_tgid();
    e->ts = bpf_ktime_get_ns(); e->pid = (__u32)id; e->tgid = id >> 32; e->kind = 3;
    e->family = sk->family; e->type = sk->type; e->proto = sk->protocol; e->addr[0] = e->addr[1] = e->addr[2] = e->addr[3] = 0; e->port = 0;
    bpf_get_current_comm(e->comm, sizeof e->comm);
    bpf_ringbuf_submit(e, 0); return 1;
}
