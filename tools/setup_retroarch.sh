#!/usr/bin/env bash
# Lay ra/overlay.cfg over RetroArch's own config on the TV, and copy the core options in ra/opt.
#
#   bash tools/setup_retroarch.sh <tv-ip>[:5555]
#
# RetroArch has to have run once so its config exists. It gets stopped first, because it saves on exit.
set -euo pipefail
cd "$(dirname "$0")/.."
TV=${1:?usage: setup_retroarch.sh <tv-ip>[:5555]}
case "$TV" in *:*) ;; *) TV=$TV:5555 ;; esac
RA=com.retroarch.aarch64
CFG=/sdcard/Android/data/$RA/files/retroarch.cfg
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

adb connect "$TV" >/dev/null
A=(adb -s "$TV")
"${A[@]}" shell am force-stop "$RA"
sleep 1
"${A[@]}" pull "$CFG" "$TMP/pulled.cfg" >/dev/null
python tools/ra_merge.py "$TMP/pulled.cfg" ra/overlay.cfg "$TMP/merged.cfg"
"${A[@]}" push "$TMP/merged.cfg" "$CFG" >/dev/null
"${A[@]}" shell mkdir -p /sdcard/RetroArch/saves /sdcard/RetroArch/states
for f in ra/opt/*.opt; do
  core=$(basename "$f" .opt)
  "${A[@]}" shell mkdir -p "/sdcard/RetroArch/config/$core"
  "${A[@]}" push "$f" "/sdcard/RetroArch/config/$core/$core.opt" >/dev/null
done
echo "RetroArch set up on $TV"
