#!/bin/bash
set +x
set -euo pipefail

die() { printf '%s\n' "$*" >&2; exit 1; }

case "${1:-}" in
  "") mode=local ;;
  --dev-canary) mode=dev ;;
  *) die "Usage: bash run-jibril.sh [--dev-canary]" ;;
esac
[[ $# -le 1 ]] || die "Usage: bash run-jibril.sh [--dev-canary]"
[[ $(uname -s) == Darwin && $(uname -m) == arm64 &&
   $(sysctl -n sysctl.proc_translated 2>/dev/null || printf 0) == 0 ]] ||
  die "Run this in a native Apple Silicon macOS terminal, not under Rosetta."

version=v2.17.0
digest=05285e7ba90c64e934ebd8705b8cfd8512b5dafc0c79209d436a66f67409e3f3
dev_token=
if [[ $mode == dev ]]; then
  version=v2.13.0
  digest=98f0117f669e04034236273df8fc15d46c1ca2bd251c4064d7cd1cd20f416caf
  dev_token=${GARNET_DEV_API_TOKEN:?Set the dev project token for --dev-canary}
  [[ $dev_token != *$'\n'* ]] || die "The dev project token must be on one line."
fi
instance=${JIBRIL_LIMA_INSTANCE:-jibril-tcg}

sw_vers
uname -m
sysctl machdep.cpu.brand_string hw.model kern.hv_support
tmp=$(mktemp -d "${TMPDIR:-/tmp}/jibril-lima.XXXXXX")
trap 'rm -rf -- "$tmp"' EXIT

brew_bin=/opt/homebrew/bin/brew
if [[ ! -x $brew_bin ]]; then
  printf 'Installing Homebrew; follow any macOS authorization prompts.\n'
  curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o "$tmp/homebrew.sh"
  /bin/bash "$tmp/homebrew.sh"
fi
[[ -x $brew_bin ]] || die "Native Homebrew is not available at $brew_bin."
brew_env=$("$brew_bin" shellenv)
eval "$brew_env"
"$brew_bin" --version
missing=()
for formula in lima lima-additional-guestagents qemu; do
  if [[ -z $("$brew_bin" list --versions "$formula") ]]; then
    missing+=("$formula")
  fi
done
if [[ ${#missing[@]} -gt 0 ]]; then
  "$brew_bin" install "${missing[@]}"
fi
limactl --version
qemu-system-x86_64 --version

[[ ! -e ${LIMA_HOME:-$HOME/.lima}/$instance ]] ||
  die "Lima instance '$instance' already exists; set JIBRIL_LIMA_INSTANCE to an unused name."
printf 'Starting fresh Lima instance %s (Ubuntu 24.04, x86_64, QEMU).\n' "$instance"
limactl start --tty=false --name="$instance" --vm-type=qemu --arch=x86_64 \
  --cpus=2 --memory=4 --disk=20 --mount-none --containerd=none \
  --timeout=15m template:ubuntu-24.04
lima_shell() { limactl shell --workdir / "$instance" -- "$@"; }

curl -fsSL "https://github.com/garnet-org/jibril-releases/releases/download/$version/jibril" \
  -o "$tmp/jibril"
printf '%s  %s\n' "$digest" "$tmp/jibril" | shasum -a 256 -c -
stage=$(lima_shell mktemp -d /tmp/jibril-lima.XXXXXX)
limactl copy --backend=scp "$tmp/jibril" "$instance:$stage/jibril"
if [[ $mode == dev ]]; then
  ctl_archive=garnetctl_Linux_x86_64.tar.gz
  curl -fsSL "https://github.com/garnet-org/garnetctl-releases/releases/download/v1.19.0/$ctl_archive" \
    -o "$tmp/$ctl_archive"
  printf '71043d8bc400a6c425244a799f9f24b796bfd6277f7b3469e5f975a78428c1b9  %s\n' \
    "$tmp/$ctl_archive" | shasum -a 256 -c -
  tar -xzf "$tmp/$ctl_archive" -C "$tmp" garnetctl
  limactl copy --backend=scp "$tmp/garnetctl" "$instance:$stage/garnetctl"
fi

{
  printf '%s\n' "$dev_token"
  cat <<'GUEST'
set -euo pipefail
die() { printf '%s\n' "$*" >&2; exit 1; }

stage=$1 mode=$2 version=$3
trap 'rm -rf -- "$stage"' EXIT
. /etc/os-release
printf '%s\n' "$PRETTY_NAME"
uname -rm
[[ $(uname -m) == x86_64 ]] || die "Expected an x86-64 Linux guest."
[[ $(uname -r) == 6.8.* ]] || die "Expected an Ubuntu 6.8 kernel."
grep -x 'CONFIG_FUNCTION_TRACER=y' "/boot/config-$(uname -r)"
test -s /sys/kernel/btf/vmlinux
sudo install -m 0755 "$stage/jibril" /usr/local/bin/jibril
sudo env -i HOME=/root PATH=/usr/sbin:/usr/bin:/sbin:/bin /usr/local/bin/jibril --version

unit=jibril-local-offline
launch=(/usr/bin/env -i HOME=/root PATH=/usr/sbin:/usr/bin:/sbin:/bin
  GARNET_SAR=true GARNET_SAR_PRINTER=true /usr/local/bin/jibril)
if [[ $mode == dev ]]; then
  unit=jibril-dev-canary
  export GARNET_API_URL=https://dev-api.garnet.ai GARNET_BASE_URL=https://dev-api.garnet.ai
  [[ -n $GARNET_TOKEN ]] || die "Missing dev project token."
  sudo install -m 0755 "$stage/garnetctl" /usr/local/bin/garnetctl
  garnetctl version
  [[ $(garnetctl config current-baseurl) == "Current API base URL: $GARNET_API_URL" ]] ||
    die "garnetctl did not select the dev endpoint; refusing registration."
  printf 'Fetching merged network policy from %s.\n' "$GARNET_API_URL"
  sudo install -d -m 0755 /etc/jibril
  garnetctl get network-policy merged --format yaml --output "$stage/netpolicy.yaml" >/dev/null 2>&1 ||
    die "Could not fetch the merged policy from dev-api (CLI response withheld)."
  test -s "$stage/netpolicy.yaml"
  sudo install -m 0644 "$stage/netpolicy.yaml" /etc/jibril/netpolicy.yaml
  sudo tee /etc/jibril/config.yaml >/dev/null <<'CONFIG'
run_time:
  log-level: info
  stdout: stdout
  stderr: stderr
functionalities:
  - jibril
features:
  - hold
  - procfs
  - detect
  - enricher
  - netpolicy
feature_options:
  netpolicy:
    file: /etc/jibril/netpolicy.yaml
printers:
  - garnet
events:
  - flow
CONFIG
  run_id=$(date +%s)
  python3 - "$run_id" >"$stage/context.json" <<'CONTEXT'
import json
import sys

json.dump({
    "event_name": "workflow_dispatch",
    "ref": "refs/heads/main",
    "workflow": "macos-lima",
    "action": "__run",
    "actor": "lima",
    "job": "jibril-dev-canary",
    "run_number": "1",
    "run_id": sys.argv[1],
    "api_url": "https://api.github.com",
    "server_url": "https://github.com",
    "repository": "garnet-labs/modal-receipts",
}, sys.stdout)
CONTEXT
  read -r runner_ip _ <<<"$(hostname -I)"
  [[ -n $runner_ip ]] || die "Could not determine the Lima guest IP for the canary."
  printf 'Registering one GitHub-kind agent on dev-api (run ID %s).\n' "$run_id"
  agent_json=$(garnetctl create agent --kind github --version "${version#v}" --ip "$runner_ip" \
    --machine-id "$(cat /etc/machine-id)" --context-file "$stage/context.json" 2>/dev/null) ||
    die "Dev-api agent registration failed (CLI response withheld)."
  agent_token=$(python3 -c 'import json, sys; print(json.load(sys.stdin)["agent_token"])' \
    <<<"$agent_json" 2>/dev/null) || die "Dev-api did not return an agent token."
  [[ -n $agent_token && $agent_token != null ]] || die "Dev-api returned no usable agent token."
  unset agent_json
  mkfifo -m 0600 "$stage/credentials"
  launch=(/usr/bin/env -i HOME=/root PATH=/usr/sbin:/usr/bin:/sbin:/bin
    GARNET_API_URL="$GARNET_API_URL" GARNET_SAR=true
    GITHUB_REPOSITORY=garnet-labs/modal-receipts GITHUB_RUN_ID="$run_id"
    GITHUB_RUN_ATTEMPT=1 GITHUB_RUN_NUMBER=1 GITHUB_WORKFLOW=macos-lima
    GITHUB_JOB=jibril-dev-canary GITHUB_ACTION=__run GITHUB_ACTOR=lima
    GITHUB_REF=refs/heads/main GITHUB_EVENT_NAME=workflow_dispatch
    GITHUB_SERVER_URL=https://github.com
    /bin/bash -c '
      set -e
      { IFS= read -r GARNET_API_TOKEN; IFS= read -r GARNET_AGENT_TOKEN; } <"$1"
      export GARNET_API_TOKEN GARNET_AGENT_TOKEN
      exec /usr/local/bin/jibril --config /etc/jibril/config.yaml
    ' bash "$stage/credentials")
fi

sudo systemd-run --unit="$unit" --property=Type=exec "${launch[@]}"
if [[ $mode == dev ]]; then
  printf '%s\n' "$GARNET_TOKEN" "$agent_token" |
    timeout 30 /bin/sh -c 'cat >"$1"' sh "$stage/credentials"
  unset GARNET_TOKEN agent_token
fi
invocation=$(systemctl show --property=InvocationID --value "$unit")
[[ -n $invocation ]] || die "Could not identify the Jibril service invocation."
journal() { sudo journalctl "_SYSTEMD_INVOCATION_ID=$invocation" --no-pager -o cat; }
ready_marker="hierarchy phase 'exec' scheduled 'pkg'"
if [[ $mode == dev ]]; then
  ready_marker="agent heartbeat worker started"
fi
deadline=$((SECONDS + 180))
until [[ $(journal) == *"$ready_marker"* ]]; do
  if ! systemctl is-active --quiet "$unit" || (( SECONDS >= deadline )); then
    if [[ $mode == local ]]; then journal >&2; fi
    die "Jibril did not reach its exec phase; inspect journalctl -u $unit in the guest."
  fi
  sleep 1
done
startup=$(journal)
if [[ $mode == dev ]]; then
  printf '%s\n' "$startup" |
    grep -E 'component ebpf, phase exec set to completed|agent heartbeat worker started'
  pid=$(systemctl show --property=MainPID --value "$unit")
  [[ $pid -gt 0 ]] || die "Could not identify the Jibril service process."
  links=$(sudo /bin/sh -c 'grep -hs "^link_id:" "/proc/$1/fdinfo/"* | sort -u | wc -l' sh "$pid")
  (( links > 0 )) || die "Jibril has no live kernel eBPF links."
  attach="$links live kernel links owned by Jibril (v2.13.0 does not log an attach count)"
else
  printf '%s\n' "$startup" |
    grep -E "ebpf: (loaded [0-9]+ objects|attached [0-9]+ programs|errors: [0-9]+ load)|hierarchy phase 'exec' scheduled 'pkg'"
  attach=$(printf '%s\n' "$startup" |
    sed -nE 's/.*ebpf: attached ([0-9]+) programs, ([0-9]+) live links.*/\1 programs, \2 live links/p')
  [[ -n $attach && $attach != 0\ programs,* ]] || die "Jibril reported no attached eBPF programs."
  [[ $startup == *'ebpf: errors: 0 load, 0 attach, 0 link'* ]] || die "Jibril reported eBPF errors."
fi
systemctl is-active "$unit"
printf 'Jibril attach count: %s\n' "$attach"
GUEST
} | lima_shell /bin/bash -c '
  set +x
  IFS= read -r GARNET_TOKEN || exit 1
  export GARNET_TOKEN
  exec /bin/bash -s -- "$@"
' bash "$stage" "$mode" "$version"

printf 'Jibril is running in %s. To stop the VM: limactl stop %s\n' "$instance" "$instance"
