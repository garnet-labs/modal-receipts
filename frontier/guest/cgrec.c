#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>
struct ev { __u64 ts; __u32 pid; __u32 tgid; __u32 kind; __u32 family; __u32 type; __u32 proto; __u32 addr[4]; __u16 port; char comm[16]; };
static volatile int stop;
static void onsig(int s) { stop = 1; }
static int handle(void *c, void *d, size_t n) {
    struct ev *e = d; char a[INET6_ADDRSTRLEN] = "";
    if (e->family == 2) inet_ntop(AF_INET, e->addr, a, sizeof a); else if (e->family == 10) inet_ntop(AF_INET6, e->addr, a, sizeof a);
    printf("{\"ts\":%llu,\"kind\":\"%s\",\"pid\":%u,\"tgid\":%u,\"comm\":\"%.16s\",\"family\":%u,\"type\":%u,\"proto\":%u,\"addr\":\"%s\",\"port\":%u}\n",
        (unsigned long long)e->ts, e->kind == 1 ? "connect" : e->kind == 2 ? "sendmsg" : "sock_create", e->pid, e->tgid, e->comm, e->family, e->type, e->proto, a, e->port);
    return 0;
}
int main(int argc, char **argv) {
    const char *obj = argc > 1 ? argv[1] : "cgrec.bpf.o", *cg = argc > 2 ? argv[2] : "/sys/fs/cgroup";
    int cgfd = open(cg, O_RDONLY | O_DIRECTORY); if (cgfd < 0) { perror("cgroup"); return 1; }
    struct bpf_object *o = bpf_object__open_file(obj, NULL); if (!o) { perror("open"); return 1; }
    int err = bpf_object__load(o); if (err) { fprintf(stderr, "load: %d\n", err); return 1; }
    struct bpf_program *p; int n = 0;
    bpf_object__for_each_program(p, o) { struct bpf_link *l = bpf_program__attach_cgroup(p, cgfd); if (!l) { fprintf(stderr, "attach %s: %d\n", bpf_program__name(p), -errno); return 1; } n++; }
    fprintf(stderr, "cgrec: attached %d programs to %s\n", n, cg);
    struct ring_buffer *rb = ring_buffer__new(bpf_map__fd(bpf_object__find_map_by_name(o, "events")), handle, NULL, NULL);
    signal(SIGTERM, onsig); signal(SIGINT, onsig);
    while (!stop) { ring_buffer__poll(rb, 200); fflush(stdout); }
    ring_buffer__consume(rb); fflush(stdout); return 0;
}
