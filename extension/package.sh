#!/usr/bin/env bash
# Zips just the extension/ contents (not the whole repo, not the backend)
# for sharing or eventual Chrome Web Store upload.
set -e
cd "$(dirname "$0")"
OUT="../yt-relevance-firewall-extension.zip"
rm -f "$OUT"
zip -r -q "$OUT" . -x "README.md" -x "package.sh"
echo "Packaged to $OUT"
