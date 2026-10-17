# Compare cgroup recorder events with audit connect records for the same workload.
import json, re, sys, collections
rec = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
aud = open(sys.argv[2], errors='replace').read() if len(sys.argv) > 2 else ''
def saddr(h):
    try:
        b = bytes.fromhex(h)
    except Exception: return None
    fam = int.from_bytes(b[:2], 'little')
    if fam == 2 and len(b) >= 8: return ('.'.join(str(x) for x in b[4:8]), int.from_bytes(b[2:4], 'big'))
    if fam == 10 and len(b) >= 24:
        import ipaddress; return (str(ipaddress.IPv6Address(b[8:24])), int.from_bytes(b[2:4], 'big'))
    return None
audit = collections.Counter(); audit_pids = {}
for ev in re.split(r'\n(?=type=SYSCALL)', aud):
    if 'syscall=42' not in ev and 'syscall=connect' not in ev: continue
    m = re.search(r'saddr=([0-9A-Fa-f]+)', ev); p = re.search(r' pid=(\d+)', ev); c = re.search(r'comm="?([^" ]+)', ev)
    if not m: continue
    k = saddr(m.group(1))
    if k and k[1] not in (0,): audit[k] += 1; audit_pids[k] = (p and p.group(1), c and c.group(1))
cg = collections.Counter(); cg_pids = {}
for e in rec:
    if e['kind'] == 'connect' and e['port']: k = (e['addr'], e['port']); cg[k] += 1; cg_pids[k] = (e['tgid'], e['comm'])
out = {'cgroup_connect_events': sum(cg.values()), 'cgroup_distinct_dst': len(cg), 'audit_connect_records': sum(audit.values()), 'audit_distinct_dst': len(audit),
       'only_in_cgroup': sorted(f'{a}:{p}' for a, p in set(cg) - set(audit)), 'only_in_audit': sorted(f'{a}:{p}' for a, p in set(audit) - set(cg)),
       'kinds': dict(collections.Counter(e['kind'] for e in rec)), 'comms': dict(collections.Counter(e['comm'] for e in rec)),
       'pid_attrib_matches': sum(1 for k in set(cg) & set(audit) if str(cg_pids[k][0]) == str(audit_pids[k][0])), 'common_dst': len(set(cg) & set(audit))}
print(json.dumps(out, indent=1))
