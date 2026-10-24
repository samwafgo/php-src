#!/usr/bin/env bash
set -euo pipefail
source /etc/os-release
case "$ID" in
  ubuntu|debian)
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends libxml2 zlib1g ca-certificates python3
    ;;
  almalinux) dnf install -y libxml2 zlib ca-certificates python3 ;;
  centos)
    sed -i -e 's|^mirrorlist=|#mirrorlist=|' \
      -e 's|^#baseurl=http://mirror.centos.org/centos/\$releasever|baseurl=https://vault.centos.org/7.9.2009|' \
      /etc/yum.repos.d/CentOS-*.repo
    yum install -y libxml2 zlib ca-certificates python3 ;;
  *) exit 1 ;;
esac
