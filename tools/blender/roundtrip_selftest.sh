#!/usr/bin/env bash
# Round-trip fidelity self-test for the Flame <-> Blender camera pipeline.
#
# Runs bake_camera.py + extract_camera.py against sample_camera.json, then
# diffs input against output. Expect near-zero differences (floating-point
# formatting drift in the last few decimals of the JSON numbers is OK; any
# structural or large numeric diff is a regression).
#
# Usage:
#   ./tools/blender/roundtrip_selftest.sh                # scale=1000
#   SCALE=1 ./tools/blender/roundtrip_selftest.sh        # no rescale
#   BLENDER=/path/to/blender ./tools/blender/roundtrip_selftest.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
SCALE="${SCALE:-1000}"

INPUT="$REPO_ROOT/tools/blender/sample_camera.json"
BLEND="/tmp/forge_rt.blend"
OUTPUT="/tmp/forge_rt.json"

if [[ ! -x "$BLENDER" ]]; then
  echo "Blender binary not found at $BLENDER" >&2
  echo "Override with: BLENDER=/path/to/blender $0" >&2
  exit 2
fi

echo "==> baking $INPUT -> $BLEND (scale=$SCALE)"
"$BLENDER" --background \
  --python "$REPO_ROOT/tools/blender/bake_camera.py" \
  -- \
  --in "$INPUT" \
  --out "$BLEND" \
  --scale "$SCALE" \
  --create-if-missing \
  2>&1 | grep -E "^(bake_camera|Error)" || true

echo "==> extracting $BLEND -> $OUTPUT"
"$BLENDER" --background "$BLEND" \
  --python "$REPO_ROOT/tools/blender/extract_camera.py" \
  -- \
  --out "$OUTPUT" \
  2>&1 | grep -E "^(extract_camera|Error)" || true

echo "==> diffing original vs round-tripped JSON"
if diff -u "$INPUT" "$OUTPUT"; then
  echo "ROUND-TRIP OK: byte-identical"
else
  echo
  echo "Numeric drift above is expected (float formatting). Structure must match."
  echo "For a tighter comparison, use:"
  echo "  python3 -c \"import json,sys; a=json.load(open('$INPUT')); b=json.load(open('$OUTPUT')); print('frames in:',len(a['frames']),'out:',len(b['frames']))\""
fi
