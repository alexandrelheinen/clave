#!/usr/bin/env bash
# Build CLAVE .NET solution and Rust crate.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

export DOTNET_ROOT="${DOTNET_ROOT:-${HOME}/.dotnet}"
export PATH="${DOTNET_ROOT}:${PATH}"

echo "==> dotnet build Clave.sln"
dotnet build Clave.sln --configuration Release

echo "==> cargo build clave-core"
cargo build --manifest-path rust/clave-core/Cargo.toml

echo "Build OK."
