#!/usr/bin/env bash
# Gate verifier (Meridian). Backend unit tests + frontend TypeScript compile (D044).
# Exits 2 on failure (Meridian convention); 0 when everything passes.
#
# Frontend gate is `next build` (which runs TypeScript checking) — Playwright e2e is
# deferred to Gate 7 (tests_passing) per D044. The original D044 `tsc --noEmit` command
# is incorrect for the installed Next.js 16 typed-routes toolchain (see D052): the
# generated .next/types/validator.ts only type-checks inside next build's plugin-aware
# program; bare `tsc` cannot resolve the route registry and falsely fails.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

fail() {
  echo "run-tests: FAILED — $1" >&2
  exit 2
}

echo "[run-tests] Backend: pytest (excluding integration)"
# `uv run` resolves the workspace .venv so the gate works from a clean checkout after
# `uv sync` without manual venv activation.
uv run pytest -m "not integration" -q || fail "pytest"

if [ -d web ]; then
  echo "[run-tests] Frontend: next build (includes TypeScript check)"
  ( cd web && npx --no-install next build ) || fail "next build"
else
  echo "[run-tests] Frontend: web/ not present, skipping build"
fi

echo "[run-tests] All checks passed."
exit 0
