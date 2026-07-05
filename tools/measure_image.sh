#!/usr/bin/env bash
# L6 — Measure Docker image size by digest (inspect), not by 'docker images'.
#
# Usage:
#   ./tools/measure_image.sh <image_tag>
#   ./tools/measure_image.sh loko:v0.3.5
#
# Returns:
#   - The size in bytes via 'docker inspect --format {{.Size}}'
#   - Human-readable size (MB / GB)
#   - PASS/FAIL verdict against the 1.6 Go threshold
#
# Context (K4.3):
#   'docker images' shows the virtual/decompressed size (e.g. 3.69 Go on
#   Docker Desktop / WSL2).  'docker inspect --format {{.Size}}' shows the
#   actual on-disk layer size, which is the correct metric for V0-5.

set -euo pipefail

THRESHOLD_BYTES=$((1600 * 1024 * 1024))  # 1.6 Go = 1 677 721 600 bytes

if [ $# -lt 1 ]; then
    echo "Usage: $0 <image_tag>" >&2
    exit 2
fi

IMAGE="$1"

# Check image exists
if ! docker inspect "$IMAGE" > /dev/null 2>&1; then
    echo "ERROR: Image '$IMAGE' not found" >&2
    exit 1
fi

# Get size via inspect (actual compressed/layer size)
SIZE_BYTES=$(docker inspect --format '{{.Size}}' "$IMAGE")
SIZE_MB=$(echo "scale=2; $SIZE_BYTES / 1024 / 1024" | bc)
SIZE_GB=$(echo "scale=2; $SIZE_BYTES / 1024 / 1024 / 1024" | bc)

# Get digest
DIGEST=$(docker inspect --format '{{.Id}}' "$IMAGE" | cut -c1:20)

# Get 'docker images' size for diagnostic comparison
IMAGES_SIZE=$(docker images --format '{{.Size}}' "$IMAGE" 2>/dev/null || echo "N/A")

echo "============================================================"
echo "  LOKO Image Size Measurement (K4.3)"
echo "============================================================"
echo "  Image:            $IMAGE"
echo "  Digest:           $DIGEST..."
echo "  Size (inspect):   ${SIZE_MB} MB  (${SIZE_GB} GB)"
echo "  Size (images):    ${IMAGES_SIZE}  (decompressed, informational only)"
echo "  Threshold:        1600 MB  (1.6 GB)"

if [ "$SIZE_BYTES" -le "$THRESHOLD_BYTES" ]; then
    echo "  Verdict:          PASS"
    echo "============================================================"
    echo ""
    echo "NOTE: If 'docker images' shows a larger number, this is the"
    echo "decompressed/virtual size (typical on Docker Desktop / WSL2)."
    echo "The actual on-disk size measured by 'docker inspect' is authoritative."
    exit 0
else
    echo "  Verdict:          FAIL"
    echo "============================================================"
    echo ""
    echo "Image exceeds the 1.6 GB threshold. Run 'docker history --no-trunc $IMAGE'"
    echo "to identify large layers."
    exit 1
fi
