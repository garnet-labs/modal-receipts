"""Turn the kernel audit log + DNS log into one execution receipt (JSON on stdout).

Facts come from two in-guest sources only:
  - /var/log/audit/audit.log   kernel audit records (kauditd), key=garnet
  - /garnet/state/dns.log      answers the sandbox's own resolver returned
Nothing here infers; a chain is the recorded parent path of the process that
made the connection. Coverage is the kernel's own counters, not a claim.
"""
import json, os, re, socket, struct, sys, time
from collections import defaultdict

STATE = "/garnet/state"
AUDIT = "/var/log/audit/audit.log"
SYSCALL_NAMES = {42: "connect", 59: "execve", 322: "execveat", 56: "clone", 435: "clone3",
                 57: "fork", 58: "vfork", 231: "exit_group", 257: "openat", 2: "open",
                 85: "creat", 437: "openat2", 87: "unlink", 263: "unlinkat", 82: "rename",
                 264: "renameat", 316: "renameat2"}
MSG_RE = re.compile(r"msg=audit\((\d+\.\d+):(\d+)\)")
KV_RE = re.compile(r'(\w+)=("([^"]*)"|\S+)')


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return default


def kv(line):
    out = {}
    for m in KV_RE.finditer(line):
        out[m.group(1)] = m.group(3) if m.group(3) is not None else m.group(2)
    return out


def unhex(s):
    try:
        return bytes.fromhex(s)
    except ValueError:
        return b""


def saddr(hexs):
    b = unhex(hexs)
    if len(b) < 2:
        return None
    fam = struct.unpack("<H", b[:2])[0]
    if fam == 2 and len(b) >= 8:
        return {"family": "inet", "ip": socket.inet_ntop(socket.AF_INET, b[4:8]),
                "port": struct.unpack("!H", b[2:4])[0]}
    if fam == 10 and len(b) >= 24:
        return {"family": "inet6", "ip": socket.inet_ntop(socket.AF_INET6, b[8:24]),
                "port": struct.unpack("!H", b[2:4])[0]}
    if fam == 1:
        return {"family": "unix"}
    return {"family": str(fam)}


def decode_hex_or_str(v):
    if v is None:
        return ""
    if re.fullmatch(r"[0-9A-F]+", v) and len(v) % 2 == 0:
        return unhex(v).decode("utf-8", "replace")
    return v


def status(text):
    """`auditctl -s` prints `name value` per line."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            out[parts[0]] = parts[1]
    return out


def parse_events(t_start):
    events = {}
    order = []
    for line in open(AUDIT, errors="replace"):
        m = MSG_RE.search(line)
        if m is None:
            continue
        ts = float(m.group(1))
        if ts < t_start - 1:
            continue
        key = m.group(2)
        typ = line[5:line.index(" ")]
        if key not in events:
            events[key] = {"ts": ts, "records": []}
            order.append(key)
        events[key]["records"].append((typ, line.strip()))
    return [events[k] for k in order]


def main():
    t_start = float(read(f"{STATE}/t_start", "0") or 0)
    t_stop = float(read(f"{STATE}/t_stop", "0") or 0)
    own = set()
    for name in ("auditd.pid", "dnsproxy.pid", "recorder.pid"):
        for tok in read(f"{STATE}/{name}").split():
            if tok.isdigit():
                own.add(int(tok))
    own.add(os.getpid())

    dns = defaultdict(set)
    cname = {}
    for row in read(f"{STATE}/dns.log").splitlines():
        parts = row.split("\t")
        if len(parts) != 4:
            continue
        _, qname, name, value = parts
        if value.startswith("cname:"):
            cname[value[6:]] = qname
        elif value != "noanswer":
            dns[value].add(qname)

    procs = {}
    parent = {}
    conns = []
    files = defaultdict(lambda: {"created": 0, "written": 0, "removed": 0, "renamed": 0, "by": set()})
    n_syscall = 0
    for ev in parse_events(t_start):
        sysrec = next((kv(l) for t, l in ev["records"] if t == "SYSCALL"), None)
        if sysrec is None:
            continue
        if sysrec.get("key") != "garnet":
            continue
        n_syscall += 1
        pid = int(sysrec.get("pid", 0))
        ppid = int(sysrec.get("ppid", 0))
        if pid in own or ppid in own:
            own.add(pid)  # the recorder's own helpers and their children are not the workload
            continue
        nr = int(sysrec.get("syscall", -1))
        name = SYSCALL_NAMES.get(nr, str(nr))
        comm = sysrec.get("comm", "?")
        exe = sysrec.get("exe", "?")
        ok = sysrec.get("success") == "yes"
        parent.setdefault(pid, ppid)
        p = procs.setdefault(pid, {"pid": pid, "ppid": ppid, "comm": comm, "exe": exe,
                                   "argv": None, "first_seen": ev["ts"]})
        if name in ("execve", "execveat") and ok:
            argv = []
            for t, l in ev["records"]:
                if t == "EXECVE":
                    d = kv(l)
                    argc = int(d.get("argc", 0))
                    argv = [decode_hex_or_str(d.get(f"a{i}")) for i in range(argc)]
            p.update({"comm": comm, "exe": exe, "argv": argv, "ppid": ppid})
        elif name in ("clone", "clone3", "fork", "vfork") and ok:
            child = int(sysrec.get("exit", 0))
            if child > 0:
                parent[child] = pid
                procs.setdefault(child, {"pid": child, "ppid": pid, "comm": comm, "exe": exe,
                                         "argv": None, "first_seen": ev["ts"]})
        elif name == "connect":
            addr = None
            for t, l in ev["records"]:
                if t == "SOCKADDR":
                    d = kv(l)
                    addr = saddr(d.get("saddr", ""))
            if addr is None or addr.get("family") not in ("inet", "inet6"):
                continue
            exit_code = sysrec.get("exit", "0")
            initiated = ok or exit_code == "-115"  # EINPROGRESS: non-blocking connect under way
            conns.append({"ts": ev["ts"], "pid": pid, "comm": comm, "exe": exe, "ip": addr["ip"],
                          "port": addr["port"], "family": addr["family"], "ok": initiated,
                          "errno": None if initiated else exit_code})
        elif name in ("openat", "open", "creat", "openat2", "unlink", "unlinkat", "rename",
                      "renameat", "renameat2"):
            cwd = "/"
            for t, l in ev["records"]:
                if t == "CWD":
                    cwd = kv(l).get("cwd", "/")
            for t, l in ev["records"]:
                if t != "PATH":
                    continue
                d = kv(l)
                nm = decode_hex_or_str(d.get("name", ""))
                if nm == "" or nm.startswith("(null)"):
                    continue
                path = nm if nm.startswith("/") else os.path.normpath(os.path.join(cwd, nm))
                nt = d.get("nametype", "")
                rec = files[path]
                if nt == "CREATE":
                    rec["created"] += 1
                elif nt == "DELETE":
                    rec["removed"] += 1
                elif name.startswith("rename"):
                    rec["renamed"] += 1
                elif nt == "NORMAL" and ok and name in ("openat", "open", "creat", "openat2"):
                    rec["written"] += 1
                else:
                    continue
                rec["by"].add(comm)

    def chain(pid, depth=0):
        names = []
        seen = set()
        cur = pid
        while cur and cur not in seen and depth < 64:
            seen.add(cur)
            depth += 1
            p = procs.get(cur)
            if p is None:
                break
            names.append(p["comm"])
            cur = parent.get(cur, p["ppid"])
        return list(reversed(names))

    def name_for(ip):
        """All names the sandbox's own resolver returned this address for, as queried
        (CNAME targets are folded back to the name that was asked). Shared CDN
        addresses legitimately carry several names; the receipt keeps them all."""
        names = set()
        for n in dns.get(ip, ()):
            guard = 0
            while n in cname and guard < 16:
                n = cname[n]
                guard += 1
            names.add(n)
        if len(names) == 0:
            return None
        return " | ".join(sorted(names))

    proxy_upstream = read(f"{STATE}/upstream_dns").strip()
    destinations = {}
    for c in conns:
        if c["ip"].startswith("127.") or c["ip"] == "::1":
            c["kind"] = "loopback"
            continue
        if c["port"] == 0:
            # glibc getaddrinfo() address-selection probe: UDP connect() to port 0, no traffic
            c["kind"] = "address_probe"
            continue
        c["kind"] = "outbound"
        dom = name_for(c["ip"])
        key = f"{dom or c['ip']}:{c['port']}"
        d = destinations.setdefault(key, {"destination": dom or c["ip"], "named_by_dns": dom is not None,
                                          "port": c["port"], "addresses": set(), "attempts": 0,
                                          "initiated": 0, "chains": {}})
        d["addresses"].add(c["ip"])
        d["attempts"] += 1
        d["initiated"] += 1 if c["ok"] else 0
        ch = " > ".join(chain(c["pid"]))
        d["chains"][ch] = d["chains"].get(ch, 0) + 1
    for d in destinations.values():
        d["addresses"] = sorted(d["addresses"])
        d["chains"] = [{"chain": k, "connections": v} for k, v in sorted(d["chains"].items(), key=lambda x: -x[1])]

    st_stop = status(read(f"{STATE}/status_stop"))
    st_start = status(read(f"{STATE}/status_start"))
    rules = [r for r in read(f"{STATE}/rules").splitlines() if r.startswith("-a")]
    rules_err = [r for r in read(f"{STATE}/rules_load.log").splitlines() if r.strip() != ""]
    lost = int(st_stop.get("lost", "-1") or -1)
    enabled = st_stop.get("enabled") == "1"
    ruleset = read(f"{STATE}/ruleset").strip() or "full"
    expected_rules = 6 if ruleset == "full" else 4
    complete = enabled and lost == 0 and len(rules) == expected_rules and len(rules_err) == 0
    reasons = []
    if not enabled:
        reasons.append("audit not enabled at stop")
    if lost != 0:
        reasons.append(f"kernel reported lost={lost}")
    if len(rules) != expected_rules:
        reasons.append(f"{len(rules)}/{expected_rules} rules loaded")
    if len(rules_err) > 0:
        reasons.append("rule load errors: " + "; ".join(rules_err)[:300])

    roots = [p for p in procs.values() if parent.get(p["pid"], p["ppid"]) not in procs]
    exec_count = sum(1 for p in procs.values() if p["argv"] is not None)
    file_rows = []
    for path, rec in files.items():
        if path.startswith(("/proc/", "/dev/", "/garnet/state", "/var/log/audit")):
            continue
        file_rows.append({"path": path, "created": rec["created"], "written": rec["written"],
                          "removed": rec["removed"], "renamed": rec["renamed"], "by": sorted(rec["by"])})
    file_rows.sort(key=lambda r: r["path"])
    top = defaultdict(int)
    for r in file_rows:
        parts = r["path"].split("/")
        top["/".join(parts[:3]) if len(parts) > 3 else r["path"]] += 1

    receipt = {
        "schema": "garnet.sandbox-receipt/0.1",
        "capture": {
            "recorder": "linux-audit",
            "ruleset": ruleset,
            "kernel": read(f"{STATE}/kernel").strip(),
            "window": {"start": t_start, "stop": t_stop, "seconds": round(t_stop - t_start, 3) if t_stop else None},
            "rules": rules,
            "kernel_counters_at_stop": {k: st_stop.get(k) for k in ("enabled", "failure", "lost", "backlog", "backlog_limit", "backlog_wait_time_actual") if k in st_stop},
            "kernel_counters_at_start": {k: st_start.get(k) for k in ("lost", "backlog_limit") if k in st_start},
            "declared_complete": complete,
            "incomplete_reasons": reasons,
            "scope": ("every connect/execve/clone/exit/open-for-write/unlink/rename syscall" if ruleset == "full" else "every connect/execve/clone/exit syscall (file rules off)") + " in this VM since arming; names from the sandbox's own DNS answers; recorder processes excluded",
            "out_of_scope": ["reads", "sockets inherited from before arming", "raw/packet sockets", "kernel-internal traffic"] + ([] if ruleset == "full" else ["file writes"]),
            "syscall_records": n_syscall,
        },
        "workload": {
            "origin": read("/work/origin").strip() or None,
            "head": read("/work/head").strip() or None,
            "head_after_edit": read("/work/head_after").strip() or None,
            "results": read("/work/results").split(),
        },
        "processes": {
            "executed": exec_count,
            "total_seen": len(procs),
            "roots": [p["comm"] for p in roots][:10],
            "lineage": [{"pid": p["pid"], "ppid": parent.get(p["pid"], p["ppid"]), "comm": p["comm"],
                         "argv": (p["argv"] or [])[:8], "chain": " > ".join(chain(p["pid"]))}
                        for p in sorted(procs.values(), key=lambda p: p["first_seen"]) if p["argv"] is not None],
        },
        "network": {
            "outbound_destinations": sorted(destinations.values(), key=lambda d: (d["destination"], d["port"])),
            "outbound_connections": sum(1 for c in conns if c.get("kind") == "outbound"),
            "loopback_connections": sum(1 for c in conns if c.get("kind") == "loopback"),
            "address_probes": sum(1 for c in conns if c.get("kind") == "address_probe"),
            "unnamed_destinations": sorted({d["destination"] for d in destinations.values() if not d["named_by_dns"]}),
            "dns_upstream": proxy_upstream,
        },
        "files": {
            "paths_touched": len(file_rows),
            "by_top_level": sorted(({"prefix": k, "paths": v} for k, v in top.items()), key=lambda x: -x["paths"])[:15],
            "sample": file_rows[:60],
        },
    }
    json.dump(receipt, sys.stdout, indent=1, default=list)


if __name__ == "__main__":
    main()
