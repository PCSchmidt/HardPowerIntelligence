#!/usr/bin/env bash
# Gate verifier (Meridian). Backend unit tests + frontend TypeScript compile (D044).
# Exits 2 on failure (Meridian convention); 0 when everything passes.
#
# Frontend gate is `tsc --noEmit` only — Playwright e2e is deferred to Gate 7
# (tests_passing) per D044.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

fail() {
  echo "run-tests: FAILED — $1" >&2
  exit 2
}

echo "[run-tests] Backend: pytest (excluding integration)"
python -m pytest -m "not integration" -q || fail "pytest"

if [ -d web ]; then
  echo "[run-tests] Frontend: tsc --noEmit"
  ( cd web && npx --no-install tsc --noEmit ) || fail "tsc --noEmit"
else
  echo "[run-tests] Frontend: web/ not present, skipping tsc"
fi

echo "[run-tests] All checks passed."
exit 0
