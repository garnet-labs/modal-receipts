#!/bin/bash
# Angle A(1b), CONSTRUCTED: feed libbpf a foreign vmlinux BTF (from a 6.8 host) via
# btf_custom_path and see which Jibril programs then load/attach on this BTF-less kernel.
set -u; OUT=/out; W=/w; mkdir -p $OUT; cd $W; BTF=/w-btf/vmlinux.btf
log() { echo "[$(date -u +%FT%TZ)] $*" | tee -a $OUT/probe.log; }
log "start $(uname -r) custom btf $(stat -c %s $BTF) bytes"; uname -a > $OUT/uname.txt
mount -t bpf bpf /sys/fs/bpf 2>/dev/null; mkdir -p /sys/fs/bpf/probe
CF="-O2 -g -target bpf -D__TARGET_ARCH_x86 -I/usr/include/x86_64-linux-gnu"
clang $CF -c types.bpf.c -o types.bpf.o && gcc -O2 -o attach_probe attach_probe.c -lbpf -lelf -lz 2>/dev/null
JV=${JIBRIL_VERSION:-v2.17.0}; curl -fsSL -o jibril.tgz https://github.com/garnet-org/jibril-releases/releases/download/$JV/jibril-$JV-linux-x86_64.tar.gz && mkdir -p rel && tar xzf jibril.tgz -C rel
JB=$(find rel -type f -name jibril | head -1); python3 carve.py $JB objs > /dev/null
./attach_probe types.bpf.o /sys/fs/bpf/probe /sys/fs/cgroup $BTF > $OUT/type-probe-custombtf.jsonl 2>/dev/null; log "type probe w/ custom btf: $(grep -c '"attach":"ok"' $OUT/type-probe-custombtf.jsonl) attach ok of $(wc -l < $OUT/type-probe-custombtf.jsonl)"
: > $OUT/jibril-progs-custombtf.jsonl
for o in objs/*.o; do rm -rf /sys/fs/bpf/probe/*; timeout 120 ./attach_probe $o /sys/fs/bpf/probe /sys/fs/cgroup $BTF 2>>$OUT/jibril-progs-custombtf.err | sed "s|^{|{\"object\":\"$(basename $o)\",|" >> $OUT/jibril-progs-custombtf.jsonl; done
log "jibril programs w/ custom btf: $(wc -l < $OUT/jibril-progs-custombtf.jsonl) tried, load ok $(grep -c '"load":"ok"' $OUT/jibril-progs-custombtf.jsonl), attach ok $(grep -c '"attach":"ok"' $OUT/jibril-progs-custombtf.jsonl)"
# CO-RE relocation inventory of the network objects (which kernel types they need).
BPFTOOL=$(ls /usr/lib/linux-tools/*/bpftool 2>/dev/null | head -1); for o in objs/*.o; do n=$(grep -c . /dev/null); done
for o in objs/obj07.o objs/obj08.o objs/obj16.o; do echo "== $o"; $BPFTOOL gen min_core_btf $BTF /tmp/min.btf $o >/dev/null 2>&1 && $BPFTOOL btf dump file /tmp/min.btf 2>/dev/null | grep -E "^\[[0-9]+\] (STRUCT|UNION)" | head -20; done > $OUT/core-relocs.txt 2>&1
log done
