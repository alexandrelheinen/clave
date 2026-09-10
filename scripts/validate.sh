#!/usr/bin/env bash
# Local quality gate. CI runs this same script, so the two cannot disagree.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

fail() {
  echo "validate: $1" >&2
  exit 1
}

echo "==> [1/2] standards submodules"
for sub in standards/guidelines standards/cc-sdd; do
  [[ -f "${sub}/README.md" ]] || fail "${sub} is not checked out. Run: git submodule update --init --recursive"
done
if git submodule status --recursive | grep -q '^+'; then
  git submodule status --recursive | grep '^+' >&2
  fail "a submodule points at a commit other than the one recorded. Commit the move or reset it."
fi
echo "submodules OK"

echo "==> [2/2] rust workspace"
if [[ ! -f Cargo.toml ]]; then
  echo "no Cargo.toml yet, skipping Rust gates."
  echo "The gates land with the first crate, per standards/guidelines/languages/rs.md."
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
