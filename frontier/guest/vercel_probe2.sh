#!/bin/bash
# Angle C follow-up: namespace diagnostics + proc connector/fanotify recorder re-run (no self-feedback).
set -u; OUT=/tmp/out2; W=/tmp/w; mkdir -p $OUT; cd $W
{ echo "pid=$$"; grep -E "NSpid|NStgid|CapEff|CapBnd|Uid" /proc/self/status; ls -l /proc/self/ns/ | awk '{print $9,$10,$11}'; ls -l /proc/1/ns/ 2>&1 | awk '{print $9,$10,$11}'; cat /proc/1/comm; grep -E "CapEff" /proc/1/status; cat /proc/sys/kernel/unprivileged_userns_clone 2>&1; cat /proc/self/uid_map; cat /proc/sys/net/core/rmem_default; } > $OUT/ns.txt 2>&1
gcc -O2 -o pcrec pcrec.c 2> $OUT/gcc.err || echo "pcrec build failed"
./pcrec / > $OUT/pcrec.jsonl 2> $OUT/pcrec.err & PCPID=$!; sleep 1
for i in 1 2 3; do /bin/true; /usr/bin/id -u > /dev/null; curl -sS -o /dev/null https://example.com; python3 -c "print(1)" > /dev/null; done; echo x > /tmp/w/touched2.txt; sleep 2
kill $PCPID; wait $PCPID 2>/dev/null; cat $OUT/pcrec.err
python3 - <<'PY' > $OUT/pcrec-summary.json
import json,collections
c=collections.Counter(); ex=[]; fe=[]
for l in open('/tmp/out2/pcrec.jsonl'):
    e=json.loads(l); c[(e['src'], (e.get('ev') or e.get('mask','')).strip())]+=1
    if e['src']=='cn_proc' and e.get('ev')=='exec': ex.append(e)
    if e['src']=='fanotify' and 'exec' in e.get('mask',''): fe.append(e)
print(json.dumps({'by_src_ev':{f'{a}/{b}':v for (a,b),v in c.items()},'cn_proc_exec_samples':ex[:8],'fanotify_exec_samples':fe[:8],'curl_exec_seen_by':{'cn_proc':sum(1 for e in ex if e.get('comm')=='curl'),'fanotify':sum(1 for e in fe if 'curl' in e.get('path',''))}},indent=1))
PY
cat $OUT/ns.txt; cat $OUT/pcrec-summary.json | head -60
