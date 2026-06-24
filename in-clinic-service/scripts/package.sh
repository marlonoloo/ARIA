#!/usr/bin/env bash
# Package a handler into a Lambda-deployable zip.
#
# Usage:
#   scripts/package.sh clinical_briefing            -> build/clinical_briefing.zip
#   scripts/package.sh diagnostic_recommendation    -> build/diagnostic_recommendation.zip
#
# The zip contains the shared/ package + the selected handler. boto3 is provided
# by the Lambda runtime, so it is intentionally NOT bundled.
set -euo pipefail

HANDLER="${1:?Usage: package.sh <clinical_briefing|diagnostic_recommendation>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/src"
BUILD="$ROOT/build"
STAGE="$BUILD/stage_$HANDLER"

if [[ ! -f "$SRC/handlers/$HANDLER.py" ]]; then
  echo "Unknown handler: $HANDLER" >&2
  exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE/handlers" "$STAGE/shared"

cp "$SRC/shared/"*.py "$STAGE/shared/"
cp "$SRC/handlers/__init__.py" "$STAGE/handlers/"
cp "$SRC/handlers/$HANDLER.py" "$STAGE/handlers/"

mkdir -p "$BUILD"
( cd "$STAGE" && zip -q -r "$BUILD/$HANDLER.zip" . )
rm -rf "$STAGE"

echo "Built $BUILD/$HANDLER.zip"
echo "Lambda handler string: handlers.$HANDLER.handler"
