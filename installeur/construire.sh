#!/usr/bin/env bash
# Construit Installer-Jarvis.exe (sous Linux ou Windows avec NSIS 3 et Python installés).
#   Linux : sudo apt install nsis
#   Windows : installer NSIS depuis nsis.sourceforge.io, puis lancer ce script dans Git Bash.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
BUILD=$(mktemp -d)
STAGE="$BUILD/stage"
mkdir -p "$STAGE"

# 1. Fichiers de l'application
cp -r jarvis plugins Jarvis.pyw jarvis.ico README.md NOUVEAUTES.md VERSION .env.example "$STAGE/"
cp installeur/requirements-windows.txt "$STAGE/"
find "$STAGE" -name "__pycache__" -prune -exec rm -rf {} +

# 2. uv.exe (installe Python et les bibliothèques chez l'utilisateur)
python3 -m pip download uv --platform win_amd64 --only-binary=:all: --no-deps -d "$BUILD/uv" -q
(cd "$BUILD/uv" && unzip -q -o uv-*.whl)
cp "$BUILD"/uv/uv-*.data/scripts/uv.exe "$STAGE/"

# 3. Installeur (le script .nsi est en UTF-8 : on ajoute le BOM attendu par NSIS)
printf '\xef\xbb\xbf' > "$BUILD/jarvis.nsi"
cat installeur/jarvis.nsi >> "$BUILD/jarvis.nsi"
makensis -V2 -DVERSION="$(cat VERSION)" -DSTAGE="$STAGE" -DOUTFILE="$ROOT/Installer-Jarvis.exe" "$BUILD/jarvis.nsi"
rm -rf "$BUILD"
echo "OK : $ROOT/Installer-Jarvis.exe"
