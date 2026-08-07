#!/usr/bin/env bash
# Local quality gate matching CI: .NET build+test and Rust tests.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

export DOTNET_ROOT="${DOTNET_ROOT:-${HOME}/.dotnet}"
export PATH="${DOTNET_ROOT}:${PATH}"

echo "==> [1/3] dotnet build Clave.sln"
dotnet build Clave.sln

echo "==> [2/3] dotnet test Clave.sln"
dotnet test Clave.sln --no-build

echo "==> [3/3] cargo test --manifest-path rust/clave-core/Cargo.toml"
cargo test --manifest-path rust/clave-core/Cargo.toml

echo "validate: OK"
