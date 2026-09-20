#!/usr/bin/env bash
# Local quality gate. CI runs this same script, so the two cannot disagree.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

fail() {
  echo "validate: $1" >&2
  exit 1
}

echo "==> [1/3] guidelines submodule"
for sub in .guidelines; do
  [[ -f "${sub}/README.md" ]] || fail "${sub} is not checked out. Run: git submodule update --init --recursive"
done
if git submodule status --recursive | grep -q '^+'; then
  git submodule status --recursive | grep '^+' >&2
  fail "a submodule points at a commit other than the one recorded. Commit the move or reset it."
fi
echo "submodules OK"

echo "==> [1b/3] merge conflict markers"
# A conflict marker committed into a tracked file is invisible to every other
# gate: ruff and mypy never see Markdown, and a corrupted document still renders.
# One slipped into a committed document and survived a merge to main.
if git grep -nE '^(<<<<<<< |={7}$|>>>>>>> )' -- . ':!.guidelines' ':!third_party' >/dev/null 2>&1; then
  git grep -nE '^(<<<<<<< |={7}$|>>>>>>> )' -- . ':!.guidelines' ':!third_party' >&2
  fail "a merge conflict marker is committed in a tracked file"
fi
echo "no conflict markers"

echo "==> [2/3] python platform"
if [[ ! -f pyproject.toml ]]; then
  echo "no pyproject.toml yet, skipping Python gates."
else
  PY_RUN=""
  if [[ -x .venv/bin/python ]]; then
    PY_RUN=".venv/bin/"
  elif ! command -v ruff >/dev/null 2>&1; then
    fail "ruff not found and no .venv present. See ./scripts/setup.sh"
  fi

  "${PY_RUN}ruff" check src tests
  "${PY_RUN}ruff" format --check src tests
  "${PY_RUN}mypy"
  "${PY_RUN}pytest" --cov=clave --cov-report=term-missing --cov-fail-under=80 -q

  echo "--- corpus manifest ---"
  "${PY_RUN}python" -m clave.cli verify-manifest
  echo "python OK"
fi

echo "==> [3/3] rust workspace"
if [[ ! -f Cargo.toml ]]; then
  echo "no Cargo.toml yet, skipping Rust gates."
  echo "The gates land with the first crate, per .guidelines/languages/rs.md."
  echo "validate: OK"
  exit 0
fi

command -v cargo >/dev/null 2>&1 || fail "cargo not found. See ./scripts/setup.sh"

cargo fmt --all --check
cargo clippy --all-targets --all-features -- -D warnings
cargo nextest run --all-features
cargo test --doc
RUSTDOCFLAGS="-D warnings" cargo doc --no-deps --all-features
cargo deny check
cargo llvm-cov --all-features --fail-under-lines 80

echo "validate: OK"
