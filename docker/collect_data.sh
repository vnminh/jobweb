#!/usr/bin/env bash
# Stage the runtime data of the recommender for the backend image (maintainers only).
#   docker/collect_data.sh /path/to/jobunicorn/data [/path/to/title_text_w7.npz]
# Copies the files listed in docker/data_files.txt (~2.1 GB) to docker/assets/data and the encoder cache to docker/assets/cache.
set -euo pipefail
SRC="${1:?usage: $0 <jobunicorn/data> [title_text_w7.npz]}"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$HERE/assets"
mkdir -p "$OUT/data" "$OUT/cache"
while read -r f; do
  [ -z "$f" ] && continue
  mkdir -p "$OUT/data/$(dirname "$f")"
  cp -u "$SRC/$f" "$OUT/data/$f"
done < "$HERE/data_files.txt"
[ -n "${2:-}" ] && cp -u "$2" "$OUT/cache/"
du -sh "$OUT/data" "$OUT/cache"
