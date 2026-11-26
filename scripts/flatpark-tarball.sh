#!/bin/sh
# Packs the Python parts of a Handset Flatpak build into the archive FlatPark installs
# (attach it to each GitHub release under this exact name). FlatPark runs it on the
# same org.kde.Platform runtime with: PYTHONPATH=<archive>/site-packages python3 -m handset
# Usage: scripts/flatpark-tarball.sh [path to the build's files/ dir, default: installed app]
set -eu
files="${1:-$(flatpak info -l io.github.kennyporto.Handset//master)/files}"
sp="$files/lib/python3.13/site-packages"
out="$PWD/handset-linux-x86_64-flatpark.tar.gz"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
dst="$tmp/site-packages"; mkdir -p "$dst/PySide6" "$dst/shiboken6"

cp -r "$sp/handset" "$sp/jeepney" "$dst/"
cp "$sp"/shiboken6/*.py "$sp"/shiboken6/*.so* "$dst/shiboken6/"
cp "$sp"/PySide6/*.py "$sp"/PySide6/libpyside6*.so* "$dst/PySide6/"
# PySide6/Qt is left out: only FFmpeg (for QtMultimedia) and build tools, Handset needs neither.
# The modules Handset imports, and the ones they load.
for m in QtCore QtGui QtNetwork QtOpenGL QtQml QtQuick QtQuickControls2 QtWidgets; do
    cp "$sp/PySide6/$m.abi3.so" "$dst/PySide6/"
done
find "$dst" -name __pycache__ -prune -exec rm -rf {} +
tar --owner=0 --group=0 -czf "$out" -C "$tmp" site-packages
ls -lh "$out"
