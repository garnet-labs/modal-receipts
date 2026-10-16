#!/bin/bash
# N sequential HTTPS GETs, a new TCP connection each time; per-request curl timings.
# $1 = count, $2 = URL. Used to measure per-connection relay cost (with vs without sidecar).
set -u
N="${1:-200}"; URL="${2:-https://registry.npmjs.org/-/ping}"
mkdir -p /work; cd /work
echo "::step https $N $URL"
for _ in $(seq "$N"); do
  curl -s -o /dev/null --no-keepalive -m 20 -w '%{time_connect} %{time_appconnect} %{time_total} %{http_code}\n' "$URL"
done > /work/times.txt
echo "::times_total $(awk '{printf "%s,", $3}' /work/times.txt)"
echo "::times_connect $(awk '{printf "%s,", $1}' /work/times.txt)"
echo "::codes $(awk '{print $4}' /work/times.txt | sort | uniq -c | tr -s ' \n' ' ')"
echo "::done rc=0"
