#!/usr/bin/env bash
# Disposable build/runtime containers only. Keep package signature verification.
set -euo pipefail
source /etc/os-release
if [[ "$ID" == debian && "$VERSION_ID" == 11 ]]; then
  mkdir -p /etc/apt/ci-disabled-sources
  shopt -s nullglob
  for file in /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do
    mv "$file" /etc/apt/ci-disabled-sources/
  done
  # Minimal Debian images do not yet have ca-certificates. HTTP is supported
  # by the official archive; APT still authenticates signed indexes/packages.
  cat > /etc/apt/sources.list <<'SOURCES'
deb [check-valid-until=no] http://archive.debian.org/debian bullseye main
deb [check-valid-until=no] http://archive.debian.org/debian-security bullseye-security main
SOURCES
  # Discard indexes that still select packages removed from the live CDN.
  rm -rf /var/lib/apt/lists/*
  echo 'Debian 11: using official archived base and security repositories'
fi
