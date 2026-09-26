#!/usr/bin/env bash
# Install the project environment, then train one corpus-run configuration.
# --clean deletes that candidate's checkpoint files first, so the next run
# starts at epoch 1. Without it, a finished epoch is resumed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT}"

step() { echo "==> $1"; }
fail() { echo "ERROR: $1" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: examples/corpus-run/train.sh [--clean] [--lite] [--config PATH]

Installs the virtualenv, the Python extras, the release safety layer, and
the object meshes, then trains one configuration.

  --clean        Remove that candidate's checkpoint, run record, and picks
  --lite         Train examples/corpus-run/classification-lite.yml
  --config PATH  Training file (default: examples/corpus-run/classification.yml)
EOF
}

CONFIG="examples/corpus-run/classification.yml"
CLEAN=0
LITE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --clean)
      CLEAN=1
      shift
      ;;
    --lite)
      LITE=1
      shift
      ;;
    --config)
      [[ $# -ge 2 ]] || fail "--config needs a path"
      CONFIG="$2"
      shift 2
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

if [[ "${LITE}" -eq 1 ]]; then
  [[ "${CONFIG}" == "examples/corpus-run/classification.yml" ]] \
    || fail "--lite already chooses the classification lite file"
  CONFIG="examples/corpus-run/classification-lite.yml"
fi

[[ -f "${CONFIG}" ]] || fail "training configuration not found: ${CONFIG}"

step "Python environment"
if [[ ! -x .venv/bin/python ]]; then
  command -v uv >/dev/null 2>&1 || fail "uv is not installed"
  uv venv .venv || fail "virtual environment creation failed"
fi
# The train command below uses whatever python and clave are on PATH.
# Sourcing is what puts the project environment there.
# shellcheck disable=SC1091
. .venv/bin/activate
hash -r

step "Install"
uv pip install -e ".[dev,world]" || fail "python dependency install failed"
cargo build --release -p clave-sitl || fail "clave-sitl release build failed"
python scripts/import_scene_assets.py --objects || fail "object asset download failed"

[[ "$(command -v python)" == "${PWD}/.venv/bin/python" ]] \
  || fail "python is not ${PWD}/.venv/bin/python"
[[ "$(command -v clave)" == "${PWD}/.venv/bin/clave" ]] \
  || fail "clave is not ${PWD}/.venv/bin/clave"

if [[ "${CLEAN}" -eq 1 ]]; then
  step "Remove the previous checkpoint"
  # These suffixes are the files the trainer writes for one candidate.
  list="$(
    python - "${CONFIG}" <<'PY'
import sys
from pathlib import Path

from clave.training.config import TrainingConfig

config = TrainingConfig.load(Path(sys.argv[1]))
suffixes = (
    ".pt",
    ".run.json",
    ".sample.json",
    ".best.pt",
    ".validation-sample.json",
)
for suffix in suffixes:
    print(config.checkpoints / f"{config.candidate}{suffix}")
PY
  )" || fail "could not read ${CONFIG}"
  while IFS= read -r path; do
    [[ -n "${path}" ]] || continue
    if [[ -e "${path}" ]]; then
      rm -f "${path}"
      echo "removed ${path}"
    else
      echo "absent ${path}"
    fi
  done <<<"${list}"
fi

step "Train"
MUJOCO_GL=osmesa clave --log-level INFO train --config "${CONFIG}" --sync
