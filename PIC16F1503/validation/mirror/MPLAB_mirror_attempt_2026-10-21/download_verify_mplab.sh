#!/usr/bin/env bash
# Obtain MPLAB X IDE v6.35 from the mirror referenced by dataspeedinc/mplabx,
# verify against the SHA-256 published by Microchip, and extract ONLY after verification.
# Does NOT execute the installer automatically.
set -euo pipefail
OUT="${1:-$PWD}"
mkdir -p "$OUT"
DEST="$OUT/MPLABX-v6.35-linux-installer.tar"
SHA='4c747363dcfb315726439f968d0e25b0b17214bb9ba5d2fd4a7f3bab28c56705'
MIRROR='https://dataspeedincorp-my.sharepoint.com/:u:/g/personal/khallenbeck_dataspeedinc_com/IQARMrlMtl4LToVZu9-EXZ12AdKSrpqxqN17H8pCn1z7SUU?download=1'
OFFICIAL='https://ww1.microchip.com/downloads/aemDocuments/documents/DEV/ProductDocuments/SoftwareTools/MPLABX-v6.35-linux-installer.tar'
if ! curl --fail --location --retry 2 --connect-timeout 30 --output "$DEST" "$MIRROR"; then
  echo 'Mirror unavailable, trying official Microchip CDN...' >&2
  curl --fail --location --retry 2 --connect-timeout 30 --output "$DEST" "$OFFICIAL"
fi
printf '%s  %s\n' "$SHA" "$DEST" | sha256sum --check --status || {
  echo 'BAD CHECKSUM: will not extract or run downloaded file' >&2
  exit 1
}
echo 'SHA-256 VERIFIED. Extracting...'
mkdir -p "$OUT/installer"
tar -xf "$DEST" -C "$OUT/installer"
echo "Installer unpacked to $OUT/installer"
echo 'Review its contents before running installer.sh.'
