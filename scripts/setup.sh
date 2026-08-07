#!/usr/bin/env bash
# Install local development toolchains for CLAVE (Phase 0).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

echo "==> CLAVE setup"

need_dotnet=0
if ! command -v dotnet >/dev/null 2>&1; then
  need_dotnet=1
else
  if ! dotnet --list-sdks 2>/dev/null | grep -q '^8\.'; then
    need_dotnet=1
  fi
fi

if [[ "${need_dotnet}" -eq 1 ]]; then
  echo "Installing .NET SDK 8.0 via dotnet-install.sh..."
  curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install-clave.sh
  bash /tmp/dotnet-install-clave.sh --channel 8.0
  export DOTNET_ROOT="${HOME}/.dotnet"
  export PATH="${DOTNET_ROOT}:${PATH}"
  echo "Add to your shell profile if needed:"
  echo "  export DOTNET_ROOT=\"\${HOME}/.dotnet\""
  echo "  export PATH=\"\${DOTNET_ROOT}:\${PATH}\""
else
  echo "dotnet OK: $(dotnet --version)"
fi

if ! command -v cargo >/dev/null 2>&1 || ! command -v rustc >/dev/null 2>&1; then
  echo "Rust toolchain (cargo/rustc) not found."
  echo "Install stable Rust from https://rustup.rs/ then re-run this script."
  exit 1
fi

echo "rustc OK: $(rustc --version)"
echo "cargo OK: $(cargo --version)"

echo "==> Restoring .NET solution"
dotnet restore Clave.sln

echo "==> Fetching Rust crate (no deps beyond std)"
cargo metadata --manifest-path rust/clave-core/Cargo.toml --no-deps >/dev/null

echo "Setup complete. Run ./scripts/validate.sh before opening a PR."
