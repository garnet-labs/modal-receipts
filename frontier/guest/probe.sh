#!/bin/bash
# Angle A guest script. Runs as root inside the Modal VM sandbox. Output in /out.
set -u; OUT=/out; W=/w; mkdir -p $OUT; cd $W
log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a $OUT/probe.log; }
log "start $(uname -r)"; uname -a > $OUT/uname.txt; cat /etc/os-release | head -2 >> $OUT/uname.txt
zcat /proc/config.gz 2>/dev/null | grep -E "^CONFIG_(BPF|BPF_SYSCALL|BPF_JIT|BPF_EVENTS|BPF_LSM|CGROUP_BPF|NET_CLS_BPF|SOCK_CGROUP_DATA|FTRACE|KPROBES|UPROBES|TRACEPOINTS|PERF_EVENTS|DEBUG_INFO_BTF|DEBUG_INFO_BTF_MODULES|MODULES|AUDIT|AUDITSYSCALL|PROC_EVENTS|FANOTIFY|LSM|SECURITY|SECURITY_NETWORK|DYNAMIC_FTRACE|FUNCTION_TRACER|HAVE_EBPF_JIT|KALLSYMS|KALLSYMS_ALL|BPF_KPROBE_OVERRIDE|BPF_PRELOAD|NETFILTER_BPF_LINK|NET_SOCK_MSG|IKCONFIG|IKHEADERS|KEXEC)(=| is not set)" > $OUT/kconfig.txt; log "kconfig lines: $(wc -l < $OUT/kconfig.txt)"
{ ls -la /sys/kernel/btf 2>&1; ls /boot 2>&1 | head; ls /lib/modules 2>&1 | head; ls -la /sys/kernel/tracing 2>&1 | head -3; mount -t tracefs none /sys/kernel/tracing 2>&1; mount -t debugfs none /sys/kernel/debug 2>&1; ls /sys/kernel/debug 2>&1 | head -3; cat /proc/kallsyms 2>/dev/null | wc -l; grep -c " T security_socket_connect" /proc/kallsyms 2>/dev/null; cat /proc/sys/kernel/perf_event_paranoid 2>&1; cat /sys/kernel/security/lsm 2>&1; cat /proc/cmdline; } > $OUT/kernel-surfaces.txt 2>&1
mount -t bpf bpf /sys/fs/bpf 2>/dev/null; mkdir -p /sys/fs/bpf/probe
BPFTOOL=$(ls /usr/lib/linux-tools/*/bpftool 2>/dev/null | head -1); [ -z "$BPFTOOL" ] && BPFTOOL=$(command -v bpftool)
$BPFTOOL version > $OUT/bpftool-feature.txt 2>&1; $BPFTOOL feature probe kernel >> $OUT/bpftool-feature.txt 2>&1; log "bpftool feature probe: $(grep -c 'is available' $OUT/bpftool-feature.txt) available / $(grep -c 'NOT available' $OUT/bpftool-feature.txt) not"
CF="-O2 -g -target bpf -D__TARGET_ARCH_x86 -I/usr/include/x86_64-linux-gnu"
clang $CF -c types.bpf.c -o types.bpf.o 2> $OUT/clang-types.err || log "types compile failed"
clang $CF -c cgrec.bpf.c -o cgrec.bpf.o 2> $OUT/clang-cgrec.err || log "cgrec compile failed"
gcc -O2 -o attach_probe attach_probe.c -lbpf -lelf -lz 2> $OUT/gcc.err || log "attach_probe build failed"
gcc -O2 -o cgrec cgrec.c -lbpf -lelf -lz 2>> $OUT/gcc.err || log "cgrec build failed"
./attach_probe types.bpf.o /sys/fs/bpf/probe > $OUT/type-probe.jsonl 2> $OUT/type-probe.err; log "type probe: $(grep -c '"attach":"ok"' $OUT/type-probe.jsonl) attach ok of $(wc -l < $OUT/type-probe.jsonl)"
# Jibril release: enumerate embedded objects and try every program on this kernel.
JV=${JIBRIL_VERSION:-v2.17.0}
curl -fsSL -o jibril.tgz https://github.com/garnet-org/jibril-releases/releases/download/$JV/jibril-$JV-linux-x86_64.tar.gz 2>$OUT/dl.err && mkdir -p rel && tar xzf jibril.tgz -C rel && find rel -maxdepth 3 | head -40 > $OUT/release-tree.txt
JB=$(find rel -type f -name jibril | head -1); log "jibril binary: $JB $(stat -c %s $JB 2>/dev/null)"; sha256sum $JB > $OUT/jibril.sha256
NOBJ=$(python3 carve.py $JB objs); log "carved $NOBJ bpf objects"
: > $OUT/jibril-sections.txt; : > $OUT/jibril-progs.jsonl
for o in objs/*.o; do echo "== $o" >> $OUT/jibril-sections.txt; llvm-readelf -S --wide $o | awk '$0 ~ /AX/ {print $2}' | sed 's/^\]//' >> $OUT/jibril-sections.txt; done
# Try fixing section names that llvm-readelf prints with index brackets.
sed -i -E 's/^\[ *[0-9]+\] *//' $OUT/jibril-sections.txt
for o in objs/*.o; do rm -rf /sys/fs/bpf/probe/*; timeout 120 ./attach_probe $o /sys/fs/bpf/probe 2>>$OUT/jibril-progs.err | sed "s|^{|{\"object\":\"$(basename $o)\",|" >> $OUT/jibril-progs.jsonl; done
log "jibril programs: $(wc -l < $OUT/jibril-progs.jsonl) tried, load ok $(grep -c '"load":"ok"' $OUT/jibril-progs.jsonl), attach ok $(grep -c '"attach":"ok"' $OUT/jibril-progs.jsonl)"
# Run the real jibril against a local API stub for raw attach log.
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
ls rel/*/ 2>/dev/null >> $OUT/release-tree.txt; CFG=$(find rel -name 'config.yaml' | head -1); echo "config: $CFG" >> $OUT/release-tree.txt; [ -n "$CFG" ] && head -60 $CFG > $OUT/release-config-head.txt
export GARNET_API_URL=http://127.0.0.1:8765 GARNET_API_TOKEN=stub GARNET_SAR=true
(cd /w && timeout 90 $JB --config /w/jibril-config.yaml > $OUT/jibril-run.log 2>&1; echo "exit=$?" >> $OUT/jibril-run.log) ; log "jibril run exit: $(tail -1 $OUT/jibril-run.log)"
grep -i -E "attach|load|fatal|error|btf|program" $OUT/jibril-run.log | head -80 > $OUT/jibril-run-excerpt.txt
# cgroup recorder vs audit.
mkdir -p /var/log/audit; (setsid auditd -n > $OUT/auditd.log 2>&1 &); sleep 1; auditctl -a always,exit -F arch=b64 -S connect -S execve >> $OUT/auditd.log 2>&1; auditctl -l >> $OUT/auditd.log 2>&1
./cgrec cgrec.bpf.o /sys/fs/cgroup > $OUT/cgrec.jsonl 2> $OUT/cgrec.err & CGPID=$!; sleep 1; cat $OUT/cgrec.err
python3 -m http.server 8099 --bind 127.0.0.1 > /dev/null 2>&1 & HPID=$!; sleep 1
workload() { curl -sS -o /dev/null https://example.com; curl -sS -o /dev/null https://pypi.org/simple/pip/; curl -sS -o /dev/null -6 https://ipv6.google.com 2>/dev/null; python3 -c "import urllib.request;urllib.request.urlopen('https://github.com',timeout=10).read(100)"; python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(b'\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x07example\x03com\x00\x00\x01\x00\x01',('8.8.8.8',53));s.settimeout(3);s.recv(512)"; getent hosts modal.com; }
log "workload start"; workload 2>> $OUT/workload.err; log "workload end"; sleep 2
for i in $(seq 1 100); do curl -sS -o /dev/null http://127.0.0.1:8099/; done; S=$(date +%s%N); for i in $(seq 1 300); do curl -sS -o /dev/null http://127.0.0.1:8099/; done; E=$(date +%s%N); echo "with_cgrec_ms=$(( (E-S)/1000000 ))" > $OUT/overhead.txt
sleep 1; kill $CGPID; wait $CGPID 2>/dev/null
S=$(date +%s%N); for i in $(seq 1 300); do curl -sS -o /dev/null http://127.0.0.1:8099/; done; E=$(date +%s%N); echo "without_cgrec_ms=$(( (E-S)/1000000 ))" >> $OUT/overhead.txt
auditctl -D >/dev/null 2>&1; sleep 1; cp /var/log/audit/audit.log $OUT/audit.log 2>/dev/null
python3 compare.py $OUT/cgrec.jsonl $OUT/audit.log > $OUT/compare.json 2>&1; log "compare: $(tr -d '\n ' < $OUT/compare.json | cut -c1-200)"
kill $HPID 2>/dev/null; log "done"
