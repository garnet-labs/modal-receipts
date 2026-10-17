#!/bin/bash
# Garnet sandbox recorder: Linux kernel audit (kauditd) + in-guest DNS forwarder.
# start  -> arm the kernel, write /garnet/state/*
# stop   -> snapshot kernel counters, print nothing else
set -u
STATE=/garnet/state
mkdir -p "$STATE"
case "${1:-}" in
  start)
    date +%s.%N > "$STATE/t_start"
    echo $$ > "$STATE/recorder.pid"
    uname -r > "$STATE/kernel"
    # one log file for the whole run: the default rotates at 8 MB and the receipt must not lose the oldest part
    sed -i 's/^max_log_file_action.*/max_log_file_action = IGNORE/; s/^max_log_file .*/max_log_file = 2048/' /etc/audit/auditd.conf 2>/dev/null || true
    setsid auditd </dev/null >/dev/null 2>&1 &
    for _ in 1 2 3 4 5 6 7 8 9 10; do pgrep -x auditd >/dev/null && break; sleep 0.1; done
    auditctl -D >/dev/null 2>&1
    auditctl -b 65536 -f 1 --backlog_wait_time 60000 >/dev/null 2>&1
    # GARNET_RULES=full (default) | nofiles : nofiles drops the open-for-write and
    # unlink/rename rules, which dominate the cost on install-heavy workloads.
    RULES="${GARNET_RULES:-full}"
    echo "$RULES" > "$STATE/ruleset"
    {
      auditctl -a always,exit -F arch=b64 -S connect -k garnet
      auditctl -a always,exit -F arch=b64 -S execve,execveat -k garnet
      auditctl -a always,exit -F arch=b64 -S clone,clone3,fork,vfork -k garnet
      auditctl -a always,exit -F arch=b64 -S exit_group -k garnet
      if [ "$RULES" = "full" ]; then
        auditctl -a always,exit -F arch=b64 -S openat,open,creat,openat2 -F a2\&3 -k garnet
        auditctl -a always,exit -F arch=b64 -S unlink,unlinkat,rename,renameat,renameat2 -k garnet
      fi
    } > "$STATE/rules_load.log" 2>&1
    auditctl -l > "$STATE/rules" 2>&1
    auditctl -s > "$STATE/status_start" 2>&1
    UP=$(awk '/^nameserver/ {print $2; exit}' /etc/resolv.conf)
    echo "$UP" > "$STATE/upstream_dns"
    cp /etc/resolv.conf "$STATE/resolv.conf.orig"
    setsid python3 /opt/garnet/dnsproxy.py "$UP" "$STATE/dns.log" </dev/null >"$STATE/dnsproxy.err" 2>&1 &
    echo $! > "$STATE/dnsproxy.pid"
    sleep 0.2
    printf 'nameserver 127.0.0.1\noptions ndots:0\n' > /etc/resolv.conf
    pgrep -x auditd > "$STATE/auditd.pid"
    echo armed
    ;;
  stop)
    echo $$ >> "$STATE/recorder.pid"
    date +%s.%N > "$STATE/t_stop"
    auditctl -s > "$STATE/status_stop" 2>&1
    sync
    ;;
  *) echo "usage: recorder.sh start|stop" >&2; exit 2;;
esac
