#!/usr/bin/env bash
# LEGACY -- the first execution model ("clone and run"). Kept to explain the
# evolution; see README.md in this directory. Not a peer option to
# runtime/image/.
#
# The executable version is decided HERE, when the task starts -- whatever
# `main` points at right now, not whatever was tested and approved at release.
set -euo pipefail

git clone --depth 1 --branch main https://github.com/efthomsen/lakehouse-runtime-demo.git workload
cd workload

uv run --script legacy/runtime-clone/example-script.py \
  --run-id "${RUN_ID}" \
  --window-start "${WINDOW_START}" \
  --window-end "${WINDOW_END}" \
  --table-uri "${TABLE_URI}"

# The lightweight-versioned-artifact tier is one line away:
#   git checkout 8a4c1d   (+ a lockfile, for deterministic dependency resolution)
# ...and still not an image: system dependencies stay on the node image,
# outside the workload's declared world.
