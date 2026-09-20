#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-android}"
DEST="$ROOT/OsmAnd/assets/palio_maps"
mkdir -p "$DEST"

FILES=(
  "Turkey_aegean_europe_2.obf.zip"
  "Turkey_black-sea_europe_2.obf.zip"
  "Turkey_central-anatolia_europe_2.obf.zip"
  "Turkey_eastern-anatolia_europe_2.obf.zip"
  "Turkey_marmara_europe_2.obf.zip"
  "Turkey_mediterranean_europe_2.obf.zip"
  "Turkey_southeastern-anatolia_europe_2.obf.zip"
)

for f in "${FILES[@]}"; do
  echo "Downloading $f"
  curl --fail --location --retry 5 --retry-delay 5 \
    "https://download.osmand.net/download?file=${f}&standard=yes" \
    --output "$DEST/$f"
  test -s "$DEST/$f"
done

echo "Downloaded Turkey offline map packages:"
du -h "$DEST"/*.zip
