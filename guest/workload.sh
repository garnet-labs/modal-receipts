#!/bin/bash
# A scripted coding-agent task on a real open-source repository:
# clone -> install -> test -> edit -> test -> commit. Key-free. Real network.
# $1 = repo url, $2 = "constructed" to seed one extra dependency fetch (labelled).
set -u
REPO="${1:?repo url}"
SEED="${2:-}"
W=/work
rm -rf "$W" && mkdir -p "$W" && cd "$W"
echo "::step clone"
git clone -q --depth 1 "$REPO" repo || exit 10
cd repo
git rev-parse HEAD > "$W/head"
git remote get-url origin > "$W/origin"
echo "::step install"
python3 -m venv .venv >/dev/null 2>&1 || exit 11
.venv/bin/pip install -q -e . pytest >/dev/null 2>&1 || exit 12
if [ "$SEED" = "constructed" ]; then
  # CONSTRUCTED: stands in for a dependency's setup hook reaching a host outside the task.
  python3 - <<'PY'
import urllib.request
urllib.request.urlopen("https://httpbin.org/get", timeout=20).read()
PY
fi
echo "::step test"
.venv/bin/pytest -q -x tests/test_basic.py >/dev/null 2>&1; echo "test1=$?" >> "$W/results"
echo "::step edit"
F=$(git ls-files 'src/*.py' | head -1)
[ -n "$F" ] || F=$(git ls-files '*.py' | head -1)
printf '\n# touched by the sandbox task\n' >> "$F"
git -c user.email=agent@sandbox -c user.name=agent commit -qam "task: annotate $F" || exit 13
git rev-parse HEAD > "$W/head_after"
echo "::step retest"
.venv/bin/pytest -q -x tests/test_basic.py >/dev/null 2>&1; echo "test2=$?" >> "$W/results"
echo "::done"
