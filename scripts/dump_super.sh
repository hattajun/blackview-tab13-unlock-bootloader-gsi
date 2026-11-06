#!/bin/bash
# Resumable, chunked dump of the `super` partition with mtkclient.
#
# A single `mtk r super super.bin` disconnected at ~6% on the Blackview Tab 13.
# Reading 1 GiB at a time worked in one connection. Completed chunks are skipped,
# so you can simply re-run after a failure (re-plug the tablet first).
#
# The offset/length below are for the Tab 13 (from `mtk printgpt`):
#   super: offset 0x2c000000, length 0x1b2800000 (user area)
#
# Usage: MTK=./venv/bin/mtk ./dump_super.sh [output_dir]
set -u
MTK="${MTK:-mtk}"
OUT="${1:-backup}"
CHUNKS="$OUT/super_chunks"
mkdir -p "$CHUNKS"

START=$((0x2c000000))
TOTAL=$((0x1b2800000))
CH=$((0x40000000))   # 1 GiB

i=0; off=0
while [ "$off" -lt "$TOTAL" ]; do
  len=$CH; [ $((TOTAL - off)) -lt "$CH" ] && len=$((TOTAL - off))
  f=$(printf "%s/super.%02d.bin" "$CHUNKS" "$i")
  if [ -f "$f" ] && [ "$(stat -c %s "$f")" -eq "$len" ]; then
    echo "chunk $i: already done"
  else
    rm -f "$f"
    echo "chunk $i: offset $(printf 0x%x $((START + off))) length $(printf 0x%x "$len")"
    timeout 900 "$MTK" ro "$(printf 0x%x $((START + off)))" "$(printf 0x%x "$len")" "$f"
    if [ "$(stat -c %s "$f" 2>/dev/null || echo 0)" -ne "$len" ]; then
      echo "chunk $i FAILED - re-plug the tablet and re-run"; rm -f "$f"; exit 1
    fi
  fi
  off=$((off + len)); i=$((i + 1))
done

cat "$CHUNKS"/super.*.bin > "$OUT/super.bin"
echo "done: $OUT/super.bin ($(stat -c %s "$OUT/super.bin") bytes, expected $TOTAL)"
