#!/usr/bin/env bash
# No package installation and no installation into the host prefix.
set -euo pipefail
src=$(cd "$1" && pwd)
out=$(realpath "$2")
profile=$3
cd "$src"
mkdir -p "$out"
exec > >(tee "$out/build.log") 2>&1
version=$(python3 ci/release/version.py)
prefix=/opt/samwaf/php56/$version
case "$profile" in
  debug-test) extra=(--enable-debug);;
  web-release) extra=(--disable-debug --enable-filter --enable-json --enable-hash
    --enable-mbstring --enable-bcmath --enable-sockets --enable-ctype
    --enable-tokenizer --enable-pdo --with-mysqli=mysqlnd --with-pdo-mysql=mysqlnd
    --with-mysql=mysqlnd --with-zlib --enable-libxml --enable-dom --enable-xml
    --enable-simplexml --enable-xmlreader --enable-xmlwriter);;
  *) echo "Unknown profile: $profile" >&2; exit 1;;
esac
export CFLAGS="-O2 -fno-strict-aliasing -fwrapv -fcommon ${CFLAGS:-}"
${CC:-cc} $CFLAGS -I. ci/multibuild/test_multiply.c -o "$out/test-multiply"
"$out/test-multiply" | tee "$out/multiply-smoke.txt"
./buildconf --force
./configure --prefix="$prefix" --with-config-file-path="$prefix/etc" \
  --with-config-file-scan-dir="$prefix/etc/conf.d" --disable-all \
  --enable-cli --enable-cgi --enable-fpm --enable-session --without-pear "${extra[@]}" \
  > "$out/configure.log" 2>&1 || { tail -n 100 "$out/configure.log"; exit 1; }
make -j"${BUILD_JOBS:-2}" > "$out/make.log" 2>&1 || { tail -n 100 "$out/make.log"; exit 1; }
chmod 0755 sapi/cli/php sapi/cgi/php-cgi sapi/fpm/php-fpm
./sapi/cli/php -n -v | tee "$out/version.txt"
grep -Fq "PHP $version" "$out/version.txt"
./sapi/cli/php -n -m > "$out/modules.txt"
./sapi/cli/php -n -i > "$out/php-info.txt"
grep -Fq 'max_multipart_body_parts' "$out/php-info.txt"
./sapi/cli/php -n -r 'if (PHP_VERSION !== $argv[1] || !extension_loaded("session")) exit(1); echo "runtime-ok\n";' -- "$version"
if [[ "$profile" == web-release ]]; then
  ./sapi/cli/php -n -r '$mods=array("filter","json","hash","mbstring","bcmath","sockets","ctype","tokenizer","PDO","mysqli","pdo_mysql","mysql","zlib","libxml","dom","xml","SimpleXML","xmlreader","xmlwriter"); foreach($mods as $m) if(!extension_loaded($m)){fwrite(STDERR,"Missing: ".$m."\n");exit(1);} echo "modules-ok\n";'
fi
for bin in sapi/cli/php sapi/cgi/php-cgi sapi/fpm/php-fpm; do
  ldd "$bin" >> "$out/ldd.txt"
done
if grep -F 'not found' "$out/ldd.txt"; then exit 1; fi
cp /etc/os-release "$out/os-release"
uname -m > "$out/architecture.txt"
getconf GNU_LIBC_VERSION > "$out/glibc.txt"
${CC:-cc} --version > "$out/compiler.txt"
printf '%s\n' "${CFLAGS}" > "$out/cflags.txt"
printf '%s\n' --prefix="$prefix" --with-config-file-path="$prefix/etc" \
  --with-config-file-scan-dir="$prefix/etc/conf.d" --disable-all --enable-cli \
  --enable-cgi --enable-fpm --enable-session --without-pear "${extra[@]}" > "$out/configure-args.txt"
export NO_INTERACTION=1 SKIP_SLOW_TESTS=1 SKIP_ONLINE_TESTS=1 REPORT_EXIT_STATUS=1
export TEST_PHP_EXECUTABLE="$src/sapi/cli/php"
export TEST_PHP_CGI_EXECUTABLE="$src/sapi/cgi/php-cgi"
set +e
./sapi/cli/php -n run-tests.php -n Zend/tests ext/session/tests tests/basic > "$out/tests.log" 2>&1
rc=$?
set -e
printf '%s\n' "$rc" > "$out/test-exit-code.txt"
tail -n 65 "$out/tests.log"
mkdir -p "$out/failed-tests"
while IFS= read -r -d '' file; do
  rel=${file#./}
  mkdir -p "$out/failed-tests/$(dirname "$rel")"
  cp "$file" "$out/failed-tests/$rel"
done < <(find Zend/tests ext/session/tests tests/basic -type f \
  \( -name '*.diff' -o -name '*.out' -o -name '*.exp' -o -name '*.log' -o -name '*.sh' \) -print0)
# INSTALL_ROOT is a staging directory; /opt and running services are not touched.
stage="$out/stage"
mkdir -p "$stage"
make install INSTALL_ROOT="$stage" > "$out/install.log" 2>&1
mkdir -p "$out/package"
cp -a "$stage$prefix/." "$out/package/"
mkdir -p "$out/package/etc/conf.d"
cp php.ini-production "$out/package/etc/php.ini.example"
cp LICENSE "$out/package/LICENSE"
rm -rf "$stage"
