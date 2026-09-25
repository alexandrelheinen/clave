#!/usr/bin/env bash
# Report what CLAVE development needs and how to install what is missing.
# This script does not install toolchains silently.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

missing=0

report() {
  local name="$1" hint="$2"
  if command -v "${name}" >/dev/null 2>&1; then
    printf '  ok      %-16s %s\n' "${name}" "$(${name} --version 2>&1 | head -1)"
  else
    printf '  MISSING %-16s %s\n' "${name}" "${hint}"
    missing=1
  fi
}

echo "==> Submodules"
if [[ -f .guidelines/README.md ]]; then
  echo "  ok      guidelines checked out"
else
  echo "  fetching guidelines submodule"
  git submodule update --init --recursive
fi

echo "==> Object meshes"
if [[ -f third_party/scanned_objects/models/JarroSil_Activated_Silicon/model.obj ]]; then
  echo "  ok      pinned object files present"
else
  printf '  MISSING object meshes. Fetch them with:\n'
  printf '            python scripts/import_scene_assets.py --objects\n'
  missing=1
fi

echo "==> Toolchain"
report git "install from your package manager"
report cargo "install a stable Rust toolchain from https://rustup.rs"

echo "==> Cargo tools required by the quality gate"
if command -v cargo >/dev/null 2>&1; then
  for tool in nextest llvm-cov deny; do
    if cargo "${tool}" --version >/dev/null 2>&1; then
      printf '  ok      cargo-%s\n' "${tool}"
    else
      printf '  MISSING cargo-%s   install with: cargo install cargo-%s --locked\n' "${tool}" "${tool}"
      missing=1
    fi
  done
else
  echo "  skipped, cargo is not installed yet"
fi

echo "==> Python platform tooling"
if [[ -f pyproject.toml ]]; then
  if [[ -x .venv/bin/ruff ]]; then
    echo "  ok      .venv with the dev toolchain"
  else
    printf '  MISSING python dev toolchain. Create it with:\n'
    printf '            uv venv .venv && . .venv/bin/activate && uv pip install -e ".[dev]"\n'
    missing=1
  fi
else
  echo "  skipped, no pyproject.toml yet"
fi

echo "==> Agent toolchain"
echo "  See AGENTS.md for agent instructions."

if [[ "${missing}" -ne 0 ]]; then
  echo
  echo "Setup incomplete. Install what is marked MISSING above, then re-run."
  exit 1
fi

echo
echo "Setup complete. Run ./scripts/validate.sh before opening a pull request."
