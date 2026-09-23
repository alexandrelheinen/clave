#!/usr/bin/env bash
# Prepare a Cursor Cloud Agent VM to develop, test, and run CLAVE.
#
# This script is the `install` phase of .cursor/environment.json. It runs once
# after the repository is checked out and must stay idempotent: a second run
# against a warm machine reinstalls nothing it can detect is already present.
# It installs the headless OpenGL stack MuJoCo renders through, the uv-managed
# Python environment, every pinned submodule (including the 2 GB scanned-object
# meshes the world is built from), the cargo tools the quality gate calls, and
# the release safety-layer binary the runtime bridge loads.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

step() { echo "==> $1"; }
fail() { echo "ERROR: $1" >&2; exit 1; }

step "System libraries for headless MuJoCo rendering"
# MuJoCo renders through OSMesa on a machine with no display, which the test
# suite pins with MUJOCO_GL=osmesa. The libraries are stable, so they are
# installed here only when the OSMesa runtime is absent.
if ! ldconfig -p | grep -q "libOSMesa.so"; then
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libosmesa6 libgl1 libglx-mesa0 libegl1 \
    || fail "system OpenGL libraries failed to install"
else
  echo "OSMesa already present"
fi

step "Rust toolchain pinned by rust-toolchain.toml"
command -v cargo >/dev/null 2>&1 || fail "cargo not found; the base image must ship rustup"
# Touching the toolchain makes rustup fetch the pinned channel and the rustfmt,
# clippy, and llvm-tools-preview components the gate needs before first use.
rustup show >/dev/null || fail "the pinned Rust toolchain failed to install"

step "uv package manager"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh || fail "uv install failed"
fi
export PATH="${HOME}/.local/bin:${PATH}"
command -v uv >/dev/null 2>&1 || fail "uv is not on PATH after install"

step "Pinned submodules (guidelines, arm, warehouse, YCB and scanned objects)"
# The scanned-object meshes are about 2 GB and the world refuses to build
# without them, so the full recursive fetch is part of a usable environment.
git submodule update --init --recursive || fail "submodule checkout failed"

step "Python environment with the dev and world extras"
if [[ ! -x .venv/bin/python ]]; then
  uv venv .venv || fail "virtual environment creation failed"
fi
# The world extra pulls MuJoCo; the dev extra pulls ruff, mypy, pytest and the
# decoders the gate exercises on every run.
uv pip install --python .venv/bin/python -e ".[dev,world]" \
  || fail "python dependency install failed"

step "Cargo tools the quality gate runs"
# cargo install is a no-op that exits zero when the pinned tool is already
# present, so this stays idempotent across reruns.
cargo install --locked cargo-nextest cargo-llvm-cov cargo-deny \
  || fail "cargo gate tooling failed to install"

step "Release safety-layer binary the runtime bridge loads"
cargo build --release -p clave-sitl || fail "clave-sitl release build failed"

echo
echo "Install complete. Activate the environment with: . .venv/bin/activate"
echo "Render headless simulations with MUJOCO_GL=osmesa (the test suite sets it for you)."
