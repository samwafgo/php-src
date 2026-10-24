#!/usr/bin/env bash
# Executed only inside the disposable build container.
set -euo pipefail
source /etc/os-release
bash "$(dirname "$0")/configure-repos.sh"
case "$ID:$VERSION_ID" in
  ubuntu:*|debian:*)
    export DEBIAN_FRONTEND=noninteractive
    apt-get -o Acquire::Retries=3 update
    apt-get install -y --no-install-recommends autoconf automake libtool \
      build-essential pkg-config perl ca-certificates libxml2-dev zlib1g-dev python3
    ;;
  almalinux:*)
    dnf install -y gcc gcc-c++ make autoconf automake libtool \
      pkgconf-pkg-config perl ca-certificates libxml2-devel zlib-devel tar gzip diffutils findutils python3
    ;;
  centos:7)
    # CentOS 7 is EOL; use the vendor's frozen archive, not a random mirror.
    sed -i -e 's|^mirrorlist=|#mirrorlist=|' \
      -e 's|^#baseurl=http://mirror.centos.org/centos/\$releasever|baseurl=https://vault.centos.org/7.9.2009|' \
      /etc/yum.repos.d/CentOS-*.repo
    yum install -y gcc gcc-c++ make autoconf automake libtool \
      pkgconfig perl ca-certificates libxml2-devel zlib-devel tar gzip diffutils findutils python3
    # Generated scanners are checked into this fork. No EPEL dependency needed.
    ;;
  *) echo "Unsupported container: $ID $VERSION_ID" >&2; exit 1 ;;
esac
