# PHP 5.6 Security Backport — CVE-2026-109618 / CVE-2026-109619

> 📌 **你正在查看的是安全回移分支 `PHP-5.6-CVE-2026-109618-109619`,不是上游 php-src 主分支。**
> 本 README 替换了上游构建说明;原版说明请切换到
> [`php-5.6.40`](https://github.com/php/php-src/tree/php-5.6.40) tag 查看。

> **Unofficial** community security backport of the PHP Group's emergency fixes
> (2026-10-21) to the EOL PHP 5.6 branch, following the PHP project's own
> minimal-backport approach used for 7.4 / 8.0 / 8.1.
>
> **非官方**社区安全回移。参照 PHP 官方 7.4/8.0/8.1 回移分支(`PHP-7.4-CVE-2026-109618-109619`)
> 的最小修复策略,将两项严重 RCE 漏洞修复移植到已 EOL 的 PHP 5.6 分支。

| CVE | GHSA | CVSS v4.0 | 漏洞 |
|---|---|---|---|
| CVE-2026-109618 | GHSA-w8hw-w9fx-j79w | 9.2 | OOM 内存耗尽处理异常导致 RCE |
| CVE-2026-109619 | GHSA-6wmf-4rv5-p3rp | 9.2 | 跨请求全局状态残留导致 RCE |

- 官方公告:https://www.php.net/archive/2026.php (2026-10-21)
- 官方修复版本:8.5.12 / 8.4.27 / 8.3.36 / 8.2.35
- 官方回移分支(仅源码):PHP-8.1 / PHP-8.0 / PHP-7.4 `-CVE-2026-109618-109619`
- **官方未覆盖:7.3 及更早(含全部 5.x)。本仓库即为 5.6 填补这一空白。**

---

## 补丁内容(patches/php-5.6.40-CVE-2026-109618-109619.patch,v2)

与官方 7.4 回移逐点对照(17 个文件,587 行):

| 文件 | 改动 | 对应官方 7.4 回移 |
|---|---|---|
| `Zend/zend_alloc.c` | OOM 时不再 `zend_bailout()` longjmp;新增 `zend_mm_safe_error_ex()`——直接格式化到 stderr 并 `_exit(1)` 终止 worker,由 FPM/Apache 主进程拉起干净进程;`safe_address()` 全部 6 个平台变体及 `_safe_emalloc_string()` 的整数溢出同步改用 safe_error_ex;`zend_mm_panic()` 的 `exit(1)`→`_exit(1)`(避免 atexit 钩子在损坏状态上执行) | ✅ 相同策略(v2 补齐溢出检查点) |
| `Zend/zend_alloc.h` | 导出 `zend_mm_safe_error_ex()` 声明 | ✅ |
| `Zend/zend_operators.c` | `concat_function()` / `add_string_to_string()` / `add_char_to_string()` 共 4 处 "String size overflow" 改用 safe_error_ex(7.x 在 VM 层做,5.6 在 operators 层) | ✅ 5.6 对应位置 |
| `Zend/zend_strtod.c` | `Balloc()` 失败: `zend_error(E_ERROR)` → `zend_mm_safe_error_ex()` | ✅ |
| `Zend/zend_llist.c` | `zend_llist_destroy()` 后清空 `head`/`tail` 指针 | ✅ |
| `Zend/zend_execute_API.c` | `shutdown_executor()` 末尾重置错误处理全局、`EG(exception)`、objects_store 指针 | ✅(7.4 用 ZVAL_UNDEF,5.6 用 NULL/memset) |
| `main/rfc1867.c` | multipart 头白名单(仅 Content-Disposition/Content-Type)+ 去重;新增 INI `max_multipart_body_parts`;`substring_conf` int→size_t | ✅ |
| `main/main.c` | 注册 `max_multipart_body_parts`;请求关闭后 `PG(http_globals)[i]=NULL`、`PG(modules_activated)=0` | ✅(5.6 为指针数组,置 NULL) |
| `main/SAPI.c` | `sapi_deactivate()` 中认证字段 efree 后置 NULL(防 UAF 重访) | ✅ |
| `main/php_variables.c` | 移植 `array_init_singleton`(5.6 实现:`nTableSize=2`,因 nTableMask=0 表示未初始化表),用于输入数组初始化,限制深嵌套输入的内存占用 | ✅(v2 补齐) |
| `ext/session/session.c` | rfc1867 upload-progress 的 session 写入路径 C 层强制禁用(`\|\| 1`,官方 7.4 用 `\|\| true`) | ✅ |
| `php.ini-development` / `php.ini-production` | 新增 `max_multipart_body_parts = -1` 说明 | 补充项 |
| `configure` / `configure.in` / `main/php_version.h` / `NEWS` | 版本号 5.6.40 → **5.6.40-sec1**,NEWS 条目对标官方格式 | 对标官方发布惯例 |
| `Zend/zend_types.h` SSE / `zend_vm_def.h` ZSTR_LEN 检查 / `zend_multiply.h` | PHP 7+ 数据结构(packed array / zend_string),5.6 无对应物;5.6 的等价检查点在 safe_address()(已覆盖) | ⏭️ 不适用 |

> v2 说明:初版漏掉了 `safe_address()` 系列(它在 5.6 位于 zend_alloc.c 而非头文件)、
> concat 溢出检查与 `array_init_singleton`。这些点位由社区 PR
> [php/php-src#24587](https://github.com/php/php-src/pull/24587) 独立实现验证,本版已吸收对齐。
> 与该 PR 的差异:本补丁基于 **5.6.40 正式版**(该 PR 基于 5.6.37/38-dev,缺少 5.6.39/5.6.40 的全部修复),
> 且 executor 关闭时的全局重置范围与官方 7.4 回移完全一致。

## 行为变化(必读)

1. **OOM 时进程直接终止**(`Fatal error` 输出到 stderr 后 `_exit(1)`),不再返回致命错误页面。
   FPM/mod_php 下表现为偶发 502/连接重置,worker 由主进程重新拉起——与官方 7.4 回移行为一致。
2. **`session.upload_progress` 功能在 C 层整体禁用**(无论 INI 如何设置)。
   依赖上传进度条的应用将失去进度显示(上传功能本身不受影响)。
3. 新增 INI:`max_multipart_body_parts`(默认 -1 = `max_input_vars + max_file_uploads`)。

## 验证结果(Debian 12 / gcc 12.2 / --enable-debug)

| 项目 | 结果 |
|---|---|
| 编译(CLI/CGI/FPM) | ✅ 通过,零新增告警 |
| `make test`(Zend/tests + ext/session + tests/basic,1863 例) | ✅ 1802 通过;**失败 8 例全部为 `ext/session/tests/rfc1867*.phpt`(upload_progress 功能测试,属预期行为变化)** |
| CGI multipart 实测 | ✅ `PHP_SESSION_UPLOAD_PROGRESS` 注入不再写入 `$_SESSION`;正常文件上传不受影响;非白名单头被丢弃 |
| `max_multipart_body_parts=2` 发 4 个 part | ✅ 第 3 个触发 E_WARNING 并终止解析 |
| OOM 实测(`memory_limit=2M` + 50MB 分配) | ✅ 进程直接退出(exit=1),不再 bailout |

## 构建

### Linux / macOS

```bash
tar xJf php-5.6.40.tar.xz && cd php-5.6.40
patch -p1 < /path/to/php-5.6.40-CVE-2026-109618-109619.patch
./configure --prefix=/opt/php56-sec --enable-fpm --with-mysql # 按需
make -j$(nproc)
make test   # 预期:ext/session/tests/rfc1867*.phpt 8 例失败(行为变化,见上)
sudo make install
```

### Windows(TS / NTS)

PHP 5.6 官方 Windows 二进制使用 **VC11(Visual Studio 2012)** 工具链,
发布物为 4 个包:`x86/x64 × TS(Thread Safe,Apache mod_php 用)/ NTS(IIS FastCGI、NGINX 用)`。

```
# 需要 php-sdk-binary-tools(对应 5.6 的分支)+ Visual Studio
phpsdk-vc11-x64.bat          # 或 x86
buildconf && configure --disable-all --enable-cli --enable-cgi   # NTS
buildconf && configure --disable-all --enable-cli --enable-cgi --with-zts ...  # TS(见 docs)
nmake && nmake test
```

详见 `docs/github-setup.md` 与 `.github/workflows/`。

## 免责声明

本项目为社区安全回移,**非 PHP 官方发布**。PHP 5.6 已于 2018-12-31 EOL,除本补丁外
仍有大量已知未修复漏洞。本补丁仅能封堵上述两个 CVE,长期方案仍是迁移至受支持版本。
生产环境部署前请在测试环境充分验证。
