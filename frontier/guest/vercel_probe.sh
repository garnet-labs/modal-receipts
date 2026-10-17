#!/bin/bash
# Angle C guest script for the Vercel Sandbox (run with sudo). Output in /tmp/out.
set -u; OUT=/tmp/out; W=/tmp/w; mkdir -p $OUT; cd $W
log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a $OUT/probe.log; }
log "start $(uname -r) uid=$(id -u)"; uname -a > $OUT/uname.txt; head -2 /etc/os-release >> $OUT/uname.txt
{ ls -la /sys/kernel/btf 2>&1; ls /boot /lib/modules /usr/lib/modules 2>&1 | head; ls /usr/src 2>&1; mount -t tracefs none /sys/kernel/tracing 2>&1; mount -t debugfs none /sys/kernel/debug 2>&1; ls /sys/kernel/tracing 2>&1 | head -3; wc -l < /proc/kallsyms; grep -c " T security_socket_connect" /proc/kallsyms; cat /proc/sys/kernel/perf_event_paranoid; cat /sys/kernel/security/lsm 2>&1; cat /proc/cmdline; mount -t bpf bpf /sys/fs/bpf 2>&1; cat /proc/self/cgroup; ls /sys/fs/cgroup | head -5; find / -xdev -name 'vmlinux*' -o -xdev -name 'System.map*' -o -xdev -name 'config-*' 2>/dev/null | head; dpkg -l 2>/dev/null | grep -i -E 'linux-(image|headers|tools)' | head; } > $OUT/kernel-surfaces.txt 2>&1
mkdir -p /sys/fs/bpf/probe
BPFTOOL=$(ls /usr/lib/linux-tools/*/bpftool 2>/dev/null | head -1); [ -z "$BPFTOOL" ] && BPFTOOL=$(command -v bpftool)
[ -n "$BPFTOOL" ] && { $BPFTOOL version; $BPFTOOL feature probe kernel; } > $OUT/bpftool-feature.txt 2>&1; log "bpftool: $BPFTOOL $(grep -c 'is available' $OUT/bpftool-feature.txt 2>/dev/null) available"
CF="-O2 -g -target bpf -D__TARGET_ARCH_x86 -I/usr/include/x86_64-linux-gnu"
clang $CF -c types.bpf.c -o types.bpf.o 2> $OUT/clang-types.err || log "types compile failed"
clang $CF -c cgrec.bpf.c -o cgrec.bpf.o 2> $OUT/clang-cgrec.err || log "cgrec compile failed"
gcc -O2 -o attach_probe attach_probe.c -lbpf -lelf -lz 2> $OUT/gcc.err || log "attach_probe build failed"
gcc -O2 -o cgrec cgrec.c -lbpf -lelf -lz 2>> $OUT/gcc.err || log "cgrec build failed"
gcc -O2 -o pcrec pcrec.c 2>> $OUT/gcc.err || log "pcrec build failed"
./attach_probe types.bpf.o /sys/fs/bpf/probe > $OUT/type-probe.jsonl 2> $OUT/type-probe.err; log "type probe: $(grep -c '"attach":"ok"' $OUT/type-probe.jsonl) attach ok of $(wc -l < $OUT/type-probe.jsonl)"
JV=${JIBRIL_VERSION:-v2.17.0}
curl -fsSL -o jibril.tgz https://github.com/garnet-org/jibril-releases/releases/download/$JV/jibril-$JV-linux-x86_64.tar.gz 2>$OUT/dl.err && mkdir -p rel && tar xzf jibril.tgz -C rel
JB=$(find rel -type f -name jibril | head -1); log "jibril binary: $JB"
NOBJ=$(python3 carve.py $JB objs 2>&1); log "carved $NOBJ bpf objects"
: > $OUT/jibril-progs.jsonl; for o in objs/*.o; do rm -rf /sys/fs/bpf/probe/*; timeout 120 ./attach_probe $o /sys/fs/bpf/probe 2>>$OUT/jibril-progs.err | sed "s|^{|{\"object\":\"$(basename $o)\",|" >> $OUT/jibril-progs.jsonl; done
log "jibril programs: $(wc -l < $OUT/jibril-progs.jsonl) tried, load ok $(grep -c '"load":"ok"' $OUT/jibril-progs.jsonl), attach ok $(grep -c '"attach":"ok"' $OUT/jibril-progs.jsonl)"
python3 - <<'PY' > $OUT/stub.log 2>&1 &
import json, http.server
class H(http.server.BaseHTTPRequestHandler):
    def _r(self, code, body): self.send_response(code); self.send_header('content-type','application/json'); self.end_headers(); self.wfile.write(json.dumps(body).encode())
    def do_POST(self): self.rfile.read(int(self.headers.get('content-length',0) or 0)); self._r(201, {"id":"stub","agent_token":"stub-token","status":"ok"})
    def do_GET(self): self._r(200, {"status":"ok"})
    def do_PUT(self): self.do_POST()
    def log_message(self, *a): pass
http.server.HTTPServer(('127.0.0.1', 8765), H).serve_forever()
PY
CFG=$(find rel -name 'config.yaml' | head -1); export GARNET_API_URL=http://127.0.0.1:8765 GARNET_API_TOKEN=stub GARNET_SAR=true
(cd $W && timeout 90 $JB --config $W/jibril-config.yaml > $OUT/jibril-run.log 2>&1; echo "exit=$?" >> $OUT/jibril-run.log); log "jibril run: $(tail -1 $OUT/jibril-run.log)"
# Recorders: cgroup-BPF + proc connector + fanotify, then overhead.
python3 -m http.server 8099 --bind 127.0.0.1 > /dev/null 2>&1 & HPID=$!; sleep 1
bench() { S=$(date +%s%N); for i in $(seq 1 300); do curl -sS -o /dev/null http://127.0.0.1:8099/; done; E=$(date +%s%N); echo $(( (E-S)/1000000 )); }
bench > /dev/null; echo "baseline_ms=$(bench)" > $OUT/overhead.txt
./cgrec cgrec.bpf.o /sys/fs/cgroup > $OUT/cgrec.jsonl 2> $OUT/cgrec.err & CGPID=$!; sleep 1; cat $OUT/cgrec.err
echo "cgrec_ms=$(bench)" >> $OUT/overhead.txt
./pcrec / > $OUT/pcrec.jsonl 2> $OUT/pcrec.err & PCPID=$!; sleep 1; cat $OUT/pcrec.err
echo "cgrec_plus_pcrec_ms=$(bench)" >> $OUT/overhead.txt
kill $CGPID; wait $CGPID 2>/dev/null; echo "pcrec_only_ms=$(bench)" >> $OUT/overhead.txt
./cgrec cgrec.bpf.o /sys/fs/cgroup >> $OUT/cgrec.jsonl 2>> $OUT/cgrec.err & CGPID=$!; sleep 1
log "workload start"; curl -sS -o /dev/null https://example.com; curl -sS -o /dev/null https://pypi.org/simple/pip/; python3 -c "import urllib.request;urllib.request.urlopen('https://github.com',timeout=10).read(100)"; getent hosts vercel.com; echo hi > /tmp/w/touched.txt; log "workload end"; sleep 2
kill $CGPID $PCPID; wait 2>/dev/null; kill $HPID 2>/dev/null
echo "cgrec events: $(wc -l < $OUT/cgrec.jsonl) connects: $(grep -c '"kind":"connect"' $OUT/cgrec.jsonl) ; pcrec exec: $(grep -c '"ev":"exec"' $OUT/pcrec.jsonl) fanotify: $(grep -c fanotify $OUT/pcrec.jsonl)" | tee -a $OUT/probe.log
cat $OUT/overhead.txt | tee -a $OUT/probe.log; log done
