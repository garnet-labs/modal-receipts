"""Phase-scoped Linux audit capture, executed inside the disposable guest."""

import base64
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

STATE = Path("/garnet/rollout")
AUDIT = Path("/var/log/audit/audit.log")


def command(*args):
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed: {result.stderr.strip()}")
    return result.stdout


def census():
    rows = []
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            text = path.read_text()
            fields = text[text.rindex(")") + 2 :].split()
            rows.append(
                {
                    "pid": int(path.parent.name),
                    "ppid": int(fields[1]),
                    "session": int(fields[3]),
                    "start_ticks": int(fields[19]),
                    "state": fields[0],
                    "comm": text[text.index("(") + 1 : text.rindex(")")],
                }
            )
        except (FileNotFoundError, ProcessLookupError):
            continue
    return rows


def start():
    STATE.mkdir(parents=True, exist_ok=True)
    Path("/tests").mkdir(exist_ok=True)
    config = Path("/etc/audit/auditd.conf")
    lines = config.read_text().splitlines()
    settings = {"max_log_file_action": "IGNORE", "flush": "SYNC"}
    config.write_text(
        "\n".join(
            f"{line.split('=', 1)[0].strip()} = {settings[line.split('=', 1)[0].strip()]}"
            if "=" in line and line.split("=", 1)[0].strip() in settings
            else line
            for line in lines
        )
        + "\n"
    )
    if not any(p["comm"] == "auditd" for p in census()):
        command("auditd")
    command("auditctl", "-D")
    command("auditctl", "-b", "65536")
    command(
        "auditctl",
        "-a",
        "always,exit",
        "-F",
        "arch=b64",
        "-S",
        "execve,execveat,clone,clone3,fork,vfork,exit,exit_group,setsid",
        "-k",
        "rollout_proc",
    )
    command("auditctl", "-w", "/tests", "-p", "w", "-k", "rollout_tests")
    command(
        "auditctl",
        "-a",
        "always,exit",
        "-F",
        "arch=b64",
        "-S",
        "connect",
        "-k",
        "rollout_connect",
    )
    (STATE / "dns-ready").unlink(missing_ok=True)
    with (STATE / "dns-error.log").open("w") as log:
        recorder = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).with_name("dns_capture.py")),
                str(STATE),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    (STATE / "dns-pid").write_text(str(recorder.pid))
    for _ in range(50):
        if (STATE / "dns-ready").exists() and recorder.poll() is None:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("DNS capture did not become ready")
    rules = command("auditctl", "-l")
    health = command("auditctl", "-s")
    snapshot = {
        "start": time.time(),
        "baseline": census(),
        "rules": rules,
        "status_start": health,
        "ruleset": "full-tests-dns-v1",
    }
    (STATE / "start.json").write_text(json.dumps(snapshot))
    print(json.dumps(snapshot))


def end():
    snapshot = json.loads((STATE / "start.json").read_text())
    snapshot.update(
        end=time.time(),
        census=census(),
        status_stop=command("auditctl", "-s"),
        rules_stop=command("auditctl", "-l"),
    )
    snapshot["auditd_alive"] = any(p["comm"] == "auditd" for p in snapshot["census"])
    pid = int((STATE / "dns-pid").read_text())
    alive = any(
        p["pid"] == pid and p["state"] not in ("Z", "X") for p in snapshot["census"]
    )
    if alive:
        os.kill(pid, signal.SIGTERM)
    for _ in range(30):
        dns_log = (STATE / "dns.jsonl").read_text()
        if any(
            json.loads(line).get("event") == "stop" for line in dns_log.splitlines()
        ):
            break
        time.sleep(0.1)
    snapshot["dns_capture"] = {
        "log": dns_log,
        "alive_at_freeze": alive,
        "truncated": False,
    }
    command("auditctl", "-e", "0")
    time.sleep(0.5)
    snapshot["audit_log"] = AUDIT.read_text()
    snapshot["roots"] = command_roots(
        snapshot["audit_log"], snapshot["start"], snapshot["end"]
    )
    snapshot["truncated"] = False
    print(json.dumps(snapshot))


def run(encoded):
    os.execvp("bash", ["bash", "-c", base64.b64decode(encoded).decode()])


def command_roots(log, start_time, end_time):
    events = {}
    for line in log.splitlines():
        stamp = re.search(r"msg=audit\((\d+\.\d+):(\d+)\)", line)
        if stamp and start_time <= float(stamp[1]) <= end_time:
            events.setdefault(stamp[2], []).append(line)
    roots = []
    for lines in events.values():
        if any(
            "type=EXECVE " in line
            and re.search(r'a1="?/opt/garnet/rollout_capture.py"?\s', line)
            and re.search(r'a2="?run"?(?:\s|$)', line)
            for line in lines
        ):
            for line in lines:
                if line.startswith("type=SYSCALL "):
                    match = re.search(r"\bpid=(\d+)", line)
                    if match:
                        roots.append({"pid": int(match[1])})
    return roots


if __name__ == "__main__":
    if sys.argv[1] == "start":
        start()
    elif sys.argv[1] == "end":
        end()
    elif sys.argv[1] == "run":
        run(sys.argv[2])
