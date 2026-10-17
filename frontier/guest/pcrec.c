// proc connector (exec/fork/exit with pid) + fanotify (file open/exec with pid) recorder.
// No BPF, no tracefs. Prints JSON lines until SIGTERM.
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/fanotify.h>
#include <linux/netlink.h>
#include <linux/connector.h>
#include <linux/cn_proc.h>
static volatile int stop;
static void onsig(int s) { stop = 1; }
static const char *jesc(const char *in, char *out, size_t n) { size_t j = 0; for (; *in && j + 6 < n; in++) { unsigned char c = *in; if (c == '"' || c == '\\') { out[j++] = '\\'; out[j++] = c; } else if (c < 0x20) { j += snprintf(out + j, n - j, "\\u%04x", c); } else out[j++] = c; } out[j] = 0; return out; }
static void comm_of(int pid, char *out, size_t n) { char p[64]; snprintf(p, sizeof p, "/proc/%d/comm", pid); FILE *f = fopen(p, "r"); out[0] = 0; if (f) { if (fgets(out, n, f)) out[strcspn(out, "\n")] = 0; fclose(f); } }
int main(int argc, char **argv) {
    const char *watch = argc > 1 ? argv[1] : "/";
    int nl = socket(PF_NETLINK, SOCK_DGRAM | SOCK_NONBLOCK, NETLINK_CONNECTOR);
    if (nl >= 0) {
        struct sockaddr_nl sa = { .nl_family = AF_NETLINK, .nl_groups = CN_IDX_PROC, .nl_pid = getpid() };
        if (bind(nl, (struct sockaddr *)&sa, sizeof sa) < 0) { fprintf(stderr, "proc connector bind: %s\n", strerror(errno)); close(nl); nl = -1; }
        else {
            struct { struct nlmsghdr h; struct cn_msg c; enum proc_cn_mcast_op op; } __attribute__((packed)) m = {0};
            m.h.nlmsg_len = sizeof m; m.h.nlmsg_type = NLMSG_DONE; m.h.nlmsg_pid = getpid();
            m.c.id.idx = CN_IDX_PROC; m.c.id.val = CN_VAL_PROC; m.c.len = sizeof(enum proc_cn_mcast_op); m.op = PROC_CN_MCAST_LISTEN;
            if (send(nl, &m, sizeof m, 0) < 0) { fprintf(stderr, "proc connector listen: %s\n", strerror(errno)); close(nl); nl = -1; }
            else fprintf(stderr, "proc connector: listening\n");
        }
    } else fprintf(stderr, "proc connector socket: %s\n", strerror(errno));
    int fan = fanotify_init(FAN_CLASS_NOTIF | FAN_NONBLOCK, O_RDONLY);
    int self = getpid(); unsigned long long mask = getenv("PCREC_MODIFY") ? (FAN_OPEN_EXEC | FAN_OPEN | FAN_MODIFY) : (FAN_OPEN_EXEC | FAN_OPEN);
    if (fan >= 0) {
        int rc = fanotify_mark(fan, FAN_MARK_ADD | FAN_MARK_FILESYSTEM, mask | FAN_EVENT_ON_CHILD, AT_FDCWD, watch);
        if (rc < 0) { fprintf(stderr, "fanotify_mark(FILESYSTEM %s): %s\n", watch, strerror(errno)); rc = fanotify_mark(fan, FAN_MARK_ADD | FAN_MARK_MOUNT, mask, AT_FDCWD, watch); if (rc < 0) { fprintf(stderr, "fanotify_mark(MOUNT): %s\n", strerror(errno)); close(fan); fan = -1; } else fprintf(stderr, "fanotify: mount mark on %s\n", watch); }
        else fprintf(stderr, "fanotify: filesystem mark on %s\n", watch);
    } else fprintf(stderr, "fanotify_init: %s\n", strerror(errno));
    signal(SIGTERM, onsig); signal(SIGINT, onsig);
    char buf[65536]; char comm[32];
    while (!stop) {
        struct pollfd pf[2] = { { nl, POLLIN, 0 }, { fan, POLLIN, 0 } }; poll(pf, 2, 200);
        if (nl >= 0 && (pf[0].revents & POLLIN)) {
            ssize_t n; while ((n = recv(nl, buf, sizeof buf, 0)) > 0 || (n < 0 && errno != EAGAIN && fprintf(stderr, "netlink recv: %s\n", strerror(errno)) < 0)) {
                for (struct nlmsghdr *h = (void *)buf; NLMSG_OK(h, n); h = NLMSG_NEXT(h, n)) {
                    struct cn_msg *c = NLMSG_DATA(h); struct proc_event *e = (void *)c->data;
                    if (e->what == PROC_EVENT_EXEC) { comm_of(e->event_data.exec.process_pid, comm, sizeof comm); char ec[80]; printf("{\"src\":\"cn_proc\",\"ev\":\"exec\",\"pid\":%d,\"comm\":\"%s\"}\n", e->event_data.exec.process_pid, jesc(comm, ec, sizeof ec)); }
                    else if (e->what == PROC_EVENT_FORK) printf("{\"src\":\"cn_proc\",\"ev\":\"fork\",\"pid\":%d,\"ppid\":%d}\n", e->event_data.fork.child_pid, e->event_data.fork.parent_pid);
                    else if (e->what == PROC_EVENT_EXIT) printf("{\"src\":\"cn_proc\",\"ev\":\"exit\",\"pid\":%d,\"code\":%u}\n", e->event_data.exit.process_pid, e->event_data.exit.exit_code);
                }
            }
        }
        if (fan >= 0 && (pf[1].revents & POLLIN)) {
            ssize_t n; while ((n = read(fan, buf, sizeof buf)) > 0) {
                for (struct fanotify_event_metadata *m = (void *)buf; FAN_EVENT_OK(m, n); m = FAN_EVENT_NEXT(m, n)) {
                    if (m->pid == self) { if (m->fd >= 0) close(m->fd); continue; }
                    char path[512] = ""; if (m->fd >= 0) { char l[64]; snprintf(l, sizeof l, "/proc/self/fd/%d", m->fd); ssize_t k = readlink(l, path, sizeof path - 1); if (k > 0) path[k] = 0; close(m->fd); }
                    comm_of(m->pid, comm, sizeof comm); char ec[80], ep[3100];
                    printf("{\"src\":\"fanotify\",\"mask\":\"%s%s%s\",\"pid\":%d,\"comm\":\"%s\",\"path\":\"%s\"}\n", (m->mask & FAN_OPEN_EXEC) ? "exec " : "", (m->mask & FAN_OPEN) ? "open " : "", (m->mask & FAN_MODIFY) ? "modify" : "", m->pid, jesc(comm, ec, sizeof ec), jesc(path, ep, sizeof ep));
                }
            }
        }
        fflush(stdout);
    }
    return 0;
}
