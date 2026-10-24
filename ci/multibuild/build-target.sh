#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root"
target=${1:?target required}
profile=${2:-web-release}
mode=${3:-docker}
case "$profile" in web-release|debug-test) ;; *) exit 1 ;; esac
case "$mode" in docker|native) ;; *) exit 1 ;; esac
image=$(python3 ci/multibuild/matrix.py "$target" --field image)
platform=$(python3 ci/multibuild/matrix.py "$target" --field platform)
arch=$(python3 ci/multibuild/matrix.py "$target" --field arch)
out="$root/artifacts/multibuild/$target-$profile"
if [[ -e "$out" ]]; then echo "Output exists, choose a clean checkout: $out" >&2; exit 1; fi
mkdir -p "$out"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
commit=$(git rev-parse HEAD)
python3 ci/prepare-git-patch.py --source security-backports/php-5.6.40-CVE-2026-109618-109619.patch \
  --output "$work/git.patch"
git apply --reverse --check "$work/git.patch"
grep -Fq '#define PHP_VERSION "5.6.40-sec1"' main/php_version.h
# Archive tracked source only; overlay this invocation's build tooling for local review.
mkdir "$work/src"
git archive HEAD | tar -x -C "$work/src"
cp -a ci/multibuild "$work/src/ci/"
curl -fLsS --retry 3 --connect-timeout 15 --max-time 180 \
  https://museum.php.net/php5/php-5.6.40.tar.xz -o "$work/php-5.6.40.tar.xz"
python3 ci/multibuild/prepare_parsers.py "$work/php-5.6.40.tar.xz" "$work/src" "$out/parser-provenance.json"
digest=native-host-no-container
if [[ "$mode" == native ]]; then
  python3 ci/multibuild/verify_target.py "$target"
  bash ci/multibuild/compile.sh "$work/src" "$out" "$profile"
  python3 ci/multibuild/phpt.py "$out" tests/expected-failures.txt
  bash ci/multibuild/verify-package.sh "$out/package" "$out" "$target"
else
  [[ $(uname -m) == "$arch" ]] || { echo 'Use the native runner for this CPU architecture' >&2; exit 1; }
  docker pull --platform "$platform" "$image"
  digest=$(docker image inspect "$image" --format '{{index .RepoDigests 0}}')
  # Pin both invocations to the exact downloaded digest, not the moving tag.
  docker run --rm --platform "$platform" -v "$work/src:/work" -v "$out:/out" \
    -e BUILD_JOBS="${BUILD_JOBS:-2}" -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" "$digest" bash -c \
    'trap '\''chown -R "$HOST_UID:$HOST_GID" /work /out || true'\'' EXIT
     bash /work/ci/multibuild/bootstrap.sh && bash /work/ci/multibuild/compile.sh /work /out "$1"' _ "$profile"
  python3 ci/multibuild/phpt.py "$out" tests/expected-failures.txt
  docker run --rm --platform "$platform" -v "$work/src:/work:ro" -v "$out:/out" \
    -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" "$digest" bash -c \
    'trap '\''chown -R "$HOST_UID:$HOST_GID" /out || true'\'' EXIT
     bash /work/ci/multibuild/runtime.sh && bash /work/ci/multibuild/verify-package.sh /out/package /out "$1"' _ "$target"
fi
python3 ci/multibuild/finalize.py "$out" "$target" "$profile" "$commit" "$digest" \
  security-backports/php-5.6.40-CVE-2026-109618-109619.patch
echo "Validated candidate: $out/binaries"
