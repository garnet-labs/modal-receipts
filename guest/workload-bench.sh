#!/bin/bash
# Syscall-heavy reference workload for measuring recorder overhead.
# $1 = profile: files | procs | net | repo
set -u
P="${1:-files}"
W=/work; rm -rf "$W"; mkdir -p "$W"; cd "$W"
echo "::step bench $P"
case "$P" in
  files)   # 200k open-for-write + unlink: the audit rules' hot path
    python3 - <<'PY'
import os, time
t=time.time(); n=200000
for i in range(n):
    fd=os.open(f"/work/f{i%1000}", os.O_WRONLY|os.O_CREAT, 0o644); os.close(fd)
for i in range(1000): os.unlink(f"/work/f{i}")
print(f"ops={n} seconds={time.time()-t:.3f}")
PY
    ;;
  procs)   # 5k fork+exec: lineage hot path
    t0=$(date +%s.%N); for i in $(seq 1 5000); do /bin/true; done; t1=$(date +%s.%N)
    python3 -c "print(f'ops=5000 seconds={$t1-$t0:.3f}')"
    ;;
  net)     # 2k TCP connects to a local listener: connect hot path
    python3 - <<'PY'
import socket, threading, time
srv=socket.socket(); srv.bind(("127.0.0.1",9009)); srv.listen(512)
def acc():
    while True:
        try: c,_=srv.accept(); c.close()
        except OSError: return
threading.Thread(target=acc,daemon=True).start()
t=time.time(); n=2000
for i in range(n):
    s=socket.socket(); s.connect(("127.0.0.1",9009)); s.close()
print(f"ops={n} seconds={time.time()-t:.3f}")
PY
    ;;
  repo)    # realistic: clone + npm install of a mid-size real project
    git clone -q --depth 1 https://github.com/expressjs/express repo && cd repo && \
    npm install --no-audit --no-fund --loglevel=error >/dev/null 2>&1 && echo "ops=npm-install-express"
    ;;
esac
echo "::done"
