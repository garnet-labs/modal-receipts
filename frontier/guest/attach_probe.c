// For every program in a BPF ELF object: load it alone, then try to attach it.
// Prints one JSON line per program with the libbpf/kernel error text.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdarg.h>
#include <sys/syscall.h>
#include <dirent.h>
#include <linux/perf_event.h>
#include <bpf/libbpf.h>
#include <bpf/bpf.h>

static char logbuf[4096];
static int logprint(enum libbpf_print_level lvl, const char *fmt, va_list ap) {
    char line[1024]; vsnprintf(line, sizeof line, fmt, ap);
    size_t n = strlen(logbuf), m = strlen(line);
    if (n + m + 1 >= sizeof logbuf) { memmove(logbuf, logbuf + (n + m + 1 - sizeof logbuf + 512), sizeof logbuf - (n + m + 1 - sizeof logbuf + 512)); n = strlen(logbuf); }
    memcpy(logbuf + n, line, m + 1);
    return 0;
}
static void jstr(const char *s) { putchar('"'); for (; *s; s++) { if (*s == '"' || *s == '\\') putchar('\\'); if (*s == '\n') { fputs("\\n", stdout); continue; } if ((unsigned char)*s < 0x20) continue; putchar(*s); } putchar('"'); }

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: %s obj.o pin_root [cgroup_path] [btf_custom_path]\n", argv[0]); return 2; }
    const char *path = argv[1], *pinroot = argv[2], *cgpath = argc > 3 ? argv[3] : "/sys/fs/cgroup";
    libbpf_set_print(logprint);
    libbpf_set_strict_mode(LIBBPF_STRICT_ALL);
    int cgfd = open(cgpath, O_RDONLY | O_DIRECTORY);

    LIBBPF_OPTS(bpf_object_open_opts, oo, .pin_root_path = pinroot);
    if (argc > 4) oo.btf_custom_path = argv[4];
    struct bpf_object *o = bpf_object__open_file(path, &oo);
    if (!o) { printf("{\"object\":\"%s\",\"open_error\":%d}\n", path, errno); return 1; }
    int n = 0; struct bpf_program *p;
    bpf_object__for_each_program(p, o) n++;
    char **names = calloc(n, sizeof *names); int i = 0;
    bpf_object__for_each_program(p, o) names[i++] = strdup(bpf_program__name(p));
    bpf_object__close(o);

    for (i = 0; i < n; i++) {
        DIR *d = opendir(pinroot); struct dirent *de;
        while (d && (de = readdir(d))) { if (de->d_name[0] != '.') unlinkat(dirfd(d), de->d_name, 0); }
        if (d) closedir(d);
        logbuf[0] = 0;
        o = bpf_object__open_file(path, &oo);
        if (!o) { printf("{\"program\":\"%s\",\"open_error\":%d}\n", names[i], errno); continue; }
        struct bpf_program *target = NULL;
        bpf_object__for_each_program(p, o) { if (strcmp(bpf_program__name(p), names[i]) == 0) target = p; else bpf_program__set_autoload(p, false); }
        const char *sec = bpf_program__section_name(target);
        int type = bpf_program__type(target);
        int err = bpf_object__load(o);
        printf("{\"program\":\"%s\",\"section\":\"%s\",\"prog_type\":%d,\"load\":", names[i], sec, type);
        if (err) { printf("\"error\",\"load_errno\":%d,\"load_log\":", -err); jstr(logbuf); printf("}\n"); bpf_object__close(o); fflush(stdout); continue; }
        printf("\"ok\",\"attach\":");
        logbuf[0] = 0; errno = 0;
        struct bpf_link *l = NULL; int rc = 0;
        if (strncmp(sec, "cgroup", 6) == 0) { l = bpf_program__attach_cgroup(target, cgfd); if (!l) rc = -errno; }
        else if (strncmp(sec, "sockops", 7) == 0) { l = bpf_program__attach_cgroup(target, cgfd); if (!l) rc = -errno; }
        else if (strncmp(sec, "iter", 4) == 0) { l = bpf_program__attach_iter(target, NULL); if (!l) rc = -errno; }
        else if (strncmp(sec, "uprobe", 6) == 0) { l = bpf_program__attach_uprobe(target, false, -1, "/bin/true", 0); if (!l) rc = -errno; }
        else if (strncmp(sec, "perf_event", 10) == 0) {
            struct perf_event_attr a = { .type = PERF_TYPE_SOFTWARE, .size = sizeof a, .config = PERF_COUNT_SW_CPU_CLOCK, .sample_period = 1000000 };
            int pfd = syscall(SYS_perf_event_open, &a, -1, 0, -1, 0);
            if (pfd < 0) rc = -errno; else { l = bpf_program__attach_perf_event(target, pfd); if (!l) rc = -errno; }
        } else if (strstr(names[i], "tail_") == names[i] || strncmp(sec, "classifier", 10) == 0) { printf("\"n/a (tail or classifier)\"}\n"); bpf_object__close(o); fflush(stdout); continue; }
        else { l = bpf_program__attach(target); if (!l) rc = -errno; }
        if (l) { printf("\"ok\"}\n"); bpf_link__destroy(l); }
        else { printf("\"error\",\"attach_errno\":%d,\"attach_log\":", -rc); jstr(logbuf); printf("}\n"); }
        fflush(stdout);
        bpf_object__close(o);
    }
    return 0;
}
