#!/usr/bin/env bash
set -euo pipefail
package=$(cd "$1" && pwd)
out=$(realpath "$2")
target=$3
version=$(python3 "$(dirname "$0")/../release/version.py")
python3 "$(dirname "$0")/verify_target.py" "$target"
for bin in bin/php bin/php-cgi sbin/php-fpm; do
  test -x "$package/$bin"
  ldd "$package/$bin" > "$out/$(basename "$bin")-runtime-ldd.txt"
  if grep -F 'not found' "$out/$(basename "$bin")-runtime-ldd.txt"; then exit 1; fi
  "$package/$bin" -n -v
done
"$package/bin/php" -n -r 'if(PHP_VERSION!==$argv[1])exit(1); echo "package-runtime-ok\n";' -- "$version"
python3 "$(dirname "$0")/fpm_smoke.py" "$package/sbin/php-fpm" "$out/fpm-smoke.log"
