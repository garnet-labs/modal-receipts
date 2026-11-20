#!/bin/bash
# runs as root inside the E2B guest: Devin CLI + Jibril + a node directory
set -eu
export HOME=/root DEBIAN_FRONTEND=noninteractive
mkdir -p /opt/garnet /workspace /var/log/jibril /var/run/jibril
apt-get -qq update >/dev/null 2>&1 || true
apt-get -qq install -y ffmpeg jq xz-utils >/dev/null 2>&1 || echo "apt partial"
curl -fsSL https://cli.devin.ai/install.sh -o /tmp/devin-install.sh && (bash /tmp/devin-install.sh </dev/null >/tmp/devin-install.log 2>&1 || true)
ln -sf /root/.local/bin/devin /usr/local/bin/devin && devin --version
cd /opt/garnet && curl -fsSL -o jibril.tgz https://github.com/garnet-org/jibril-releases/releases/download/v2.17.0/jibril-v2.17.0-linux-x86_64.tar.gz
echo "7a5160e4555bd526b8673f9497f0827e7ba356b8b2e3777b9cfedd4e4d2f423f  jibril.tgz" | sha256sum -c - && tar -xzf jibril.tgz jibril && chmod 755 jibril && ./jibril --version 2>&1 | head -1
echo setup-done
