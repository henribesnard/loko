#!/usr/bin/env bash
# K4: Diagnose Docker image size contradiction.
#
# Usage: tools/diag_image.sh <image_tag>
#   e.g.  tools/diag_image.sh loko-r0r1-codex:v0.3.4
#
# Outputs:
#   - docker images listing (virtual size)
#   - docker inspect .Size (actual unique bytes)
#   - docker history (per-layer breakdown)
#   - Explanation of any discrepancy
#
# The canonical size measurement for LOKO campaigns is:
#   docker inspect --format '{{.Size}}' <image_id>
# This avoids the inflated "virtual size" shown by docker images.

set -euo pipefail

TAG="${1:?Usage: $0 <image_tag>}"

echo "=== K4 Image Size Diagnostic ==="
echo "Image tag: $TAG"
echo ""

# 1. docker images (shows VIRTUAL SIZE — includes shared layers)
echo "--- docker images ---"
docker images "$TAG" --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}"
echo ""

# 2. docker inspect .Size (actual unique bytes — canonical measurement)
echo "--- docker inspect --format '{{.Size}}' ---"
INSPECT_SIZE=$(docker inspect --format '{{.Size}}' "$TAG")
INSPECT_SIZE_MB=$(echo "scale=2; $INSPECT_SIZE / 1048576" | bc)
INSPECT_SIZE_GB=$(echo "scale=3; $INSPECT_SIZE / 1073741824" | bc)
echo "  Bytes:     $INSPECT_SIZE"
echo "  Megabytes: $INSPECT_SIZE_MB MB"
echo "  Gigabytes: $INSPECT_SIZE_GB GB"
echo ""

# 3. docker history (per-layer breakdown, sorted by size)
echo "--- docker history (top 10 layers by size) ---"
docker history "$TAG" --format "table {{.Size}}\t{{.CreatedBy}}" --no-trunc | head -15
echo ""

# 4. Explanation
echo "=== Explanation ==="
echo "docker images shows the VIRTUAL SIZE which includes shared base image"
echo "layers (python:3.12-slim, node:20-alpine).  docker inspect .Size shows"
echo "the actual size of the image on disk."
echo ""
echo "For LOKO campaigns, the canonical measurement is docker inspect .Size."
echo "Target: <= 1.6 GB (1,717,986,918 bytes)."
echo ""
if [ "$INSPECT_SIZE" -le 1717986918 ]; then
    echo "PASS: $INSPECT_SIZE_GB GB <= 1.6 GB"
else
    echo "FAIL: $INSPECT_SIZE_GB GB > 1.6 GB"
fi
