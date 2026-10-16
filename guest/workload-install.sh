#!/bin/bash
# One real dependency install, the way an agent does it: fresh project, one package.
# $1 = npm|pip, $2 = package spec. Exit code is the package manager's.
set -u
ECO="${1:?npm|pip}"; PKG="${2:?package}"
W=/work; rm -rf "$W"; mkdir -p "$W"; cd "$W"
echo "::step install $ECO $PKG"
case "$ECO" in
  npm)
    npm init -y >/dev/null 2>&1
    npm install --no-audit --no-fund --loglevel=error "$PKG" >"$W/install.log" 2>&1; RC=$?
    ;;
  pip)
    python3 -m venv .venv >/dev/null 2>&1
    .venv/bin/pip install -q "$PKG" >"$W/install.log" 2>&1; RC=$?
    ;;
  *) echo "unknown ecosystem" >&2; exit 2;;
esac
echo "rc=$RC" > "$W/results"
echo "::log $(tail -c 300 "$W/install.log" | tr "\n" " ")"
echo "::files $(find "$W" -type f 2>/dev/null | wc -l)"
echo "::done rc=$RC"
exit $RC
