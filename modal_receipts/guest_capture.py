"""Phase-scoped Linux audit capture, executed inside the disposable guest."""

import base64
import json
import os
import re
import shutil
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


def integrity_watches():
    missing = {}

    def watch(flag, path, permission, key, check):
        try:
            command(
                "auditctl", "-a", "always,exit", "-F", "arch=b64",
                "-F", f"{flag}={path}", "-F", f"perm={permission}", "-k", key,
            )
        except RuntimeError:
            missing[check] = str(path)

    watch("dir", "/tests", "r", "rollout_verify_read", "verifier_read")
    workdir = Path.cwd()
    if workdir == Path("/"):
        missing["harness_write"] = "initial workdir is /"
    elif workdir != Path("/tests"):
        watch("dir", workdir, "w", "rollout_harness", "harness_write")
    for runner in ("pytest", "py.test", "tox", "nosetests", "jest", "vitest", "ctest"):
        if executable := shutil.which(runner):
            watch("path", Path(executable).resolve(), "w", "rollout_harness", "harness_write")
    try:
        objects = Path(command("git", "rev-parse", "--git-path", "objects").strip()).resolve()
    except (RuntimeError, FileNotFoundError):
        objects = workdir / ".git" / "objects"
    if objects.is_dir():
        watch("dir", objects, "r", "rollout_git_read", "git_history")
    else:
        missing["git_history"] = str(objects)
    return missing


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
    integrity_missing = integrity_watches()
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
        "integrity_missing": integrity_missing,
    }
    (STATE / "start.json").write_text(json.dumps(snapshot))
    print(json.dumps(snapshot))


def audit_flushed(marker):
    with AUDIT.open("rb") as log:
        log.seek(0, os.SEEK_END)
        log.seek(max(0, log.tell() - 65536))
        if marker.encode() not in log.read():
            return False
        os.fsync(log.fileno())
    return True


def drain_audit(timeout=60, interval=0.25):
    started = time.monotonic()
    before = command("auditctl", "-s")
    marker = f"garnet-drain-{os.getpid()}-{time.time_ns()}"
    command("auditctl", "-m", marker)
    flushed = False
    while True:
        status = command("auditctl", "-s")
        fields = dict(
            line.split(maxsplit=1) for line in status.splitlines() if " " in line
        )
        backlog = int(fields.get("backlog", "-1"))
        lost = int(fields.get("lost", "-1"))
        if backlog == 0:
            flushed = audit_flushed(marker)
        elapsed = time.monotonic() - started
        complete = (
            backlog == 0 and lost == 0 and flushed and fields.get("enabled") == "1"
        )
        timed_out = elapsed >= timeout and not complete
        if complete or timed_out or lost != 0 or fields.get("enabled") != "1":
            before_fields = dict(
                line.split(maxsplit=1) for line in before.splitlines() if " " in line
            )
            return {
                "status_before": before,
                "status_at_freeze": status,
                "backlog_before": int(before_fields.get("backlog", "-1")),
                "backlog_at_freeze": backlog,
                "lost": lost,
                "seconds": elapsed,
                "timed_out": timed_out,
                "flushed": flushed,
                "complete": complete,
            }
        time.sleep(min(interval, max(0, timeout - elapsed)))


def end():
    snapshot = json.loads((STATE / "start.json").read_text())
    snapshot.update(
        end=time.time(),
        census=census(),
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
    snapshot["rules_stop"] = command("auditctl", "-l")
    snapshot["audit_drain"] = drain_audit()
    snapshot["status_stop"] = snapshot["audit_drain"]["status_at_freeze"]
    command("auditctl", "-e", "0")
    time.sleep(0.5)
    snapshot["audit_log"] = AUDIT.read_text()
    snapshot["roots"] = command_roots(
        snapshot["audit_log"], snapshot["start"], snapshot["end"]
    )
    snapshot["truncated"] = not snapshot["audit_drain"]["complete"]
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
