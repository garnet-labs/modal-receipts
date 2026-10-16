#!/bin/bash
# One SWE-bench rollout: apply a candidate patch to the instance image, run the
# instance's FAIL_TO_PASS tests. Mirrors what an RL grader does per rollout.
# Expects /work/patch.diff, /work/test.diff, /work/tests (one test id per line).
set -u
W=/work
cd /testbed || exit 10
echo "::step apply"
git apply --whitespace=nowarn "$W/patch.diff" >"$W/apply.log" 2>&1 || { echo "::done rc=20 (patch failed)"; echo rc=20 > "$W/results"; exit 20; }
git apply --whitespace=nowarn "$W/test.diff" >>"$W/apply.log" 2>&1
echo "::step test"
# shellcheck disable=SC1091
source /opt/miniconda3/bin/activate testbed 2>/dev/null || source /opt/miniconda3/etc/profile.d/conda.sh && conda activate testbed
mapfile -t TESTS < "$W/tests"
if [ -f /testbed/tests/runtests.py ]; then
  # Django: FAIL_TO_PASS entries look like "test_name (module.Class)" -> "module.Class.test_name"
  LABELS=()
  for t in "${TESTS[@]}"; do
    if [[ "$t" =~ ^([^ ]+)\ \((.+)\)$ ]]; then LABELS+=("${BASH_REMATCH[2]}.${BASH_REMATCH[1]}"); else LABELS+=("$t"); fi
  done
  cd /testbed/tests && timeout 900 python runtests.py --verbosity 1 --parallel 1 "${LABELS[@]}" >"$W/test.log" 2>&1; RC=$?
else
  timeout 900 python -m pytest -q -p no:cacheprovider "${TESTS[@]}" >"$W/test.log" 2>&1; RC=$?
fi
echo "::log $(tail -c 300 "$W/test.log" | tr "\n" " ")"
echo "rc=$RC" > "$W/results"
echo "::done rc=$RC"
exit $RC
