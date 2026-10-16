"""Export sandbox receipts as Hugging Face Session Trace Simple Format (STS) JSONL.

    python3 export_sts.py samples/install/receipts samples/swebench out/hf

One .jsonl per receipt. The "agent" in these traces is the kernel's record of what ran:
every execve is an assistant tool call, every outbound connect() is a tool call attributed
to its process chain, the tool results are what the kernel returned. Nothing is paraphrased
from an agent transcript; this is the machine half only, and the header says so.
"""
import json, sys
from pathlib import Path

HARNESS = "garnet"  # not yet a registered HF harness id; ask HF to add it


def trace(receipt: dict, name: str) -> list:
    cap = receipt["capture"]
    wl = receipt.get("workload", {})
    lines = [{
        "type": "session", "harness": HARNESS, "id": name,
        "name": f"{name} — kernel-side execution receipt",
        "garnet": {
            "schema": receipt["schema"], "view": "kernel", "recorder": cap["recorder"],
            "kernel": cap["kernel"], "declared_complete": cap["declared_complete"],
            "incomplete_reasons": cap["incomplete_reasons"], "scope": cap["scope"],
            "out_of_scope": cap["out_of_scope"], "ruleset": cap.get("ruleset", "full"),
            "kernel_counters_at_stop": cap["kernel_counters_at_stop"],
            "substrate": "modal.com VM Sandbox (runtime=vm)",
            "workload": wl,
        },
    }]

    def msg(role, content, **kw):
        m = {"role": role, "content": content}
        m.update(kw)
        lines.append({"type": "message", "message": m})

    msg("system", "Kernel-side view only. Every tool call below is a syscall the Linux audit "
                  "subsystem recorded inside the sandbox; nothing comes from an agent transcript. "
                  f"Coverage declared by the kernel: complete={cap['declared_complete']} "
                  f"(lost={cap['kernel_counters_at_stop'].get('lost')}). Scope: {cap['scope']}")
    msg("user", f"run: {name}" + (f" (origin {wl.get('origin')}, head {wl.get('head')})" if wl.get("origin") else ""))

    n = 0
    for p in receipt["processes"]["lineage"]:
        n += 1
        tid = f"exec-{n}"
        args = {"argv": p["argv"], "chain": p["chain"], "pid": p["pid"]}
        msg("assistant", "", toolCalls=[{"id": tid, "function": {"name": "execve", "arguments": json.dumps(args)}}])
        msg("tool", f"started {p['comm']} (pid {p['pid']}) under {p['chain']}", toolCallId=tid)

    for d in receipt["network"]["outbound_destinations"]:
        for c in d["chains"]:
            n += 1
            tid = f"connect-{n}"
            args = {"destination": d["destination"], "port": d["port"], "addresses": d["addresses"],
                    "named_by_dns": d["named_by_dns"], "chain": c["chain"]}
            msg("assistant", "", toolCalls=[{"id": tid, "function": {"name": "connect", "arguments": json.dumps(args)}}])
            msg("tool", f"{c['connections']} connect() call(s) to {d['destination']}:{d['port']} from `{c['chain']}`; "
                        f"{d['initiated']}/{d['attempts']} initiated across all chains", toolCallId=tid)

    f = receipt["files"]
    n += 1
    tid = f"files-{n}"
    msg("assistant", "", toolCalls=[{"id": tid, "function": {"name": "write_files", "arguments": json.dumps({"by_top_level": f["by_top_level"]})}}])
    msg("tool", f"{f['paths_touched']} paths created/written/removed", toolCallId=tid)

    dests = receipt["network"]["outbound_destinations"]
    msg("assistant", f"{receipt['processes']['executed']} processes executed; "
                     f"{len(dests)} outbound destination(s): " + (", ".join(f"{d['destination']}:{d['port']}" for d in dests) or "none") +
                     f"; {f['paths_touched']} paths written; coverage declared complete: {cap['declared_complete']}.")
    return lines


def main():
    *srcs, out = sys.argv[1:]
    outdir = Path(out)
    outdir.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in srcs:
        for p in sorted(Path(src).glob("*.json")):
            if p.name == "cohort.json":
                continue
            receipt = json.loads(p.read_text())
            if "capture" not in receipt:
                continue
            name = p.stem
            lines = trace(receipt, name)
            (outdir / f"{name}.jsonl").write_text("\n".join(json.dumps(l) for l in lines) + "\n")
            count += 1
    print(f"wrote {count} traces to {outdir}")


if __name__ == "__main__":
    main()
