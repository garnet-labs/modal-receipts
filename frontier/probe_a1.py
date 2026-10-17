"""Angle A (Modal VM, no kernel change): which BPF program types the 7.2.9 guest
accepts, which of Jibril v2.17.0's embedded programs load/attach, and what a
cgroup-BPF-only recorder captures versus audit. Usage: modal run frontier/probe_a1.py
"""
import base64, io, os, shlex, sys, tarfile, time
import modal

HERE = os.path.dirname(os.path.abspath(__file__))
app = modal.App("jibril-frontier-a1")
image = (modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
         .apt_install("clang", "llvm", "libbpf-dev", "libelf-dev", "zlib1g-dev", "gcc", "make", "linux-tools-generic",
                      "auditd", "curl", "ca-certificates", "iproute2", "procps", "jq", "xz-utils", "bpfcc-tools"))
if os.environ.get("FRONTIER_BTF"):
    image = image.add_local_file(os.environ["FRONTIER_BTF"], "/w-btf/vmlinux.btf", copy=True)

def bundle():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        t.add(os.path.join(HERE, "guest"), arcname="w")
    return base64.b64encode(buf.getvalue()).decode()

@app.local_entrypoint()
def main(outdir: str = "", version: str = "v2.17.0", script: str = "probe.sh"):
    outdir = outdir or os.path.join(HERE, "out", "a1-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    os.makedirs(outdir, exist_ok=True)
    t0 = time.time()
    sb = modal.Sandbox.create("sleep", "infinity", app=app, image=image, runtime="vm", timeout=1500, cpu=2, memory=4096)
    print("sandbox", sb.object_id, "created in %.0fs" % (time.time() - t0))
    try:
        p = sb.exec("bash", "-c", "echo '%s' | base64 -d | tar xz -C / && ls /w" % bundle()); p.wait(); print(p.stdout.read())
        p = sb.exec("bash", "-c", "JIBRIL_VERSION=%s bash /w/%s" % (shlex.quote(version), shlex.quote(os.path.basename(script))), timeout=1200)
        for line in p.stdout: print(line, end="", flush=True)
        err = p.stderr.read(); print("rc", p.wait(), "stderr tail:", err[-2000:])
        p = sb.exec("bash", "-c", "tar czf - -C / out | base64 -w0"); data = p.stdout.read(); p.wait()
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(data)), mode="r:gz") as t:
            t.extractall(outdir)
        print("artifacts in", outdir, "total %.0fs" % (time.time() - t0))
    finally:
        sb.terminate()
