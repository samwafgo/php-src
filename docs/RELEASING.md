# PHP 5.6 安全维护与发布

## 采用的命名

| 对象 | 命名 | 用途 |
|---|---|---|
| 长期维护分支 | `PHP-5.6-security` | 累积所有已合入修复，后续都从这里继续 |
| 现有 CVE 分支 | `PHP-5.6-CVE-2026-109618-109619` | 保留历史链接；迁移后不再作为新的长期开发入口 |
| 每次修复分支 | `fix/CVE-xxxx-php56` | 从最新维护分支创建，审查后合回维护分支 |
| 程序版本 | `5.6.40-sec1`、`5.6.40-sec2` | `5.6.40` 是上游基线；`secN` 是本项目累积修订号 |
| Git Tag | `php-5.6.40-sec1`、`php-5.6.40-sec2` | 每个发布固定一个提交，不移动、不覆盖 |
| Release | `PHP 5.6.40-secN — SamWaf community backport` | 下载页面及对应资源 |

`sec2` 包含 `sec1` 的修复与之后的新改动；`sec3` 同样累积包含前两版。不要每遇到一个 CVE 都重新从官方 5.6.40 建分支，否则容易丢掉已修复内容。
`secN` 是修订号，不是漏洞数量。版本发布后需要更改二进制内容，应发布下一修订号；已有 Tag、校验和及附件保持不变。
本系列保留 `PHP_VERSION_ID=50640`；这不保证任意旧扩展可以跨架构、线程模式、编译器或配置复用。

## 当前仓库梳理（检查基准 40118a9273）

- 该仓库是完整 php-src fork，默认分支当前仍是 CVE 分支。
- Linux 15 环境最近成功运行：40106092233，源码 f10cfb1684。
- Windows 四配置最近成功运行：40155286202，源码 40118a9273。
- 两次运行不在同一提交，因此正式发布会从一个选定提交重新统一构建，避免将不同提交的产物宣称为同一 Tag。
- 已解决 Windows 补丁 CRLF、VC11 `/Fe` 旧语法、PHP 5.6 Windows x64 整数宽度和诊断上传跨盘问题。

| 文件/目录 | 职责 |
|---|---|
| `main/php_version.h`、`configure.in` | 程序实际版本；由版本脚本一致性检查 |
| `security-backports/` | 安全补丁原文和后续累计补丁 |
| `ci/release/security.json` | 上游基线、维护分支和当前累计补丁路径 |
| `ci/release/version.py` | 从源码读版本；构建、验证及包名不再写死 sec1 |
| `ci/release/bump.py` | 将 secN 升为下一修订，更新版本定义、NEWS 和新版本说明模板 |
| `ci/release/check_source.py` | 严格反向检查当前累计补丁中的源代码和 INI 修复 |
| `ci/release/update_patch.py` | 基于官方 Git 基线生成 HEAD 的累计源码补丁，固定按字节写出 |
| `.github/workflows/build-multi-php56.yml` | 15 个 Linux 原生架构/发行环境，支持独立运行或被发布调用 |
| `.github/workflows/build-multi-windows-php56.yml` | 托管 Windows、VC11、四种核心包，支持独立运行或发布调用 |
| `.github/workflows/release-php56.yml` | 同提交构建、资源核对、Tag 和 Release 发布 |
| `ci/release/assemble.py` | 要求完整 19 包，核对版本、源码 SHA、目标、校验和及内外清单 |
| `ci/release/publish.py` | 创建注释 Tag，草稿上传后核对，再正式发布；拒绝覆盖已发布版本 |
| `releases/5.6.40-secN.md` | 每版发布说明，含新增变化及验证边界 |

`apply-patch.yml`、`compare-php56.yml`、旧 `build.yml` 是最初 CVE/sec1 阶段的历史辅助流程，仍定位原 CVE 分支，不参与新的累积发版链。
已有完整补丁的维护分支不应重新运行 `apply-patch`。日常使用两个 multi 构建流程，发版使用 release-php56-sec。

## 首次接入和发布 sec1

1. 将交付包 `overlay/` 内全部内容合并到当前仓库根目录，包含 `.github/` 隐藏目录，并提交到现有默认 CVE 分支。
2. 在 GitHub 分支选择器中，从该最新提交创建 `PHP-5.6-security`，保留原分支。
3. 在仓库 Settings 中将默认分支改为 `PHP-5.6-security`。先合入工作流再迁移默认分支，确保 Actions 的手动运行入口可见。
4. 检查 `releases/5.6.40-sec1.md` 的发布说明。当前版本已是 sec1，首次不需要运行 bump。
5. 打开 Actions → `release-php56-sec` → Run workflow，选择 `PHP-5.6-security`。

工作流会执行：

1. 检查源码版本、累计补丁与发布说明。
2. 固定同一个源码 SHA，调用 Linux/Windows 构建流程。
3. 19 个包全部通过才汇总；少包、错版本、错提交、错配置、SHA256 不符都会失败。
4. 创建注释 Tag `php-5.6.40-sec1`（如果已存在则必须指向同一 SHA）。
5. 创建 Release 草稿并上传全部资源；核对名称、大小及可用的服务端 digest，再发布。

使用 GitHub 自带 GITHUB_TOKEN；只在 publish job 请求 contents:write。通常不需要 PAT、自托管 runner 或新增 secret。若组织策略禁止写权限，需要仓库管理员允许该 job 创建 Tag/Release。
工作流自行完成构建和发布，不依赖其创建的 Tag 再触发其他工作流。也支持人工推送同名版本 Tag 触发构建；这时 Tag 必须事先指向包含发布配置、正确版本和完整发布说明的提交。
已有已发布 sec1 会直接拒绝覆盖；草稿因上传中断可重试。若失败时 Tag 已创建，应重跑原运行或在该 Tag 上运行，不要把同名 Tag 改到新提交。

## Release 包含什么

- 15 个 Linux web-release 二进制 tar.gz：Ubuntu 20.04/22.04/24.04、Debian 11/12、AlmaLinux 8/9 各 x86_64/aarch64，以及 CentOS 7 x86_64。
- 4 个 Windows VC11 core zip：x86/x64 × NTS/TS。
- 同一提交的源码 tar.gz 和 zip（Git 源码，需 buildconf/CI 解析器准备）。
- `php-5.6.40-secN-security.patch`。
- 19 个构建清单及各包校验和的汇总 zip。
- `RELEASE-MANIFEST.json`：版本、Tag、源码 SHA、二进制清单和 SHA256。
- `RELEASE-NOTES.md` 与统一 `SHA256SUMS`。

包名保留 `candidate`：发到 Release 便于稳定下载，并不改变限定扩展和验证范围。Linux/Windows 依赖集、工具链下载及全量诊断日志仍在对应 Actions 中管理，不把第三方安装介质打进 Release。
Release 的累计安全补丁以官方 Git Tag 为基线，不包含生成的 configure；使用源码时需按 CI 执行 buildconf/解析器准备。最初可用于发行 tar 包的原 CVE 补丁仍留在 security-backports 作历史资料。
Release 附件中的 SHA256SUMS 覆盖其余自建附件；GitHub 自动提供的 Source code 链接属于 GitHub 生成的归档，使用另行上传并列入校验和的源码包校验。

## 将来发布 sec2

以下命令在自己的 Git 工作区执行：

```bash
git switch PHP-5.6-security
git pull --ff-only
git switch -c fix/next-security-php56
python3 ci/release/bump.py 5.6.40-sec2
```

实现新修复和对应回归测试，补齐 `releases/5.6.40-sec2.md`，提交这批源码变更。
首次准备累计补丁时，取官方 5.6.40 Git 基线作为固定参考：

```bash
git fetch --depth=1 https://github.com/php/php-src.git refs/tags/php-5.6.40:refs/tags/upstream-php-5.6.40
python3 ci/release/update_patch.py --base upstream-php-5.6.40
python3 ci/release/check_source.py
python3 ci/release/test_release.py
```

`update_patch.py` 比较的是已提交的 HEAD，请先提交源码修复；它生成 `security-backports/php-5.6.40-cumulative.patch` 并更新 security.json 的补丁路径。
范围包括 PHP 源码、配置、构建源码文件及测试，不包括项目的 CI/文档；新增其他顶层源码路径时同步扩展 SOURCE_PATHS 并审查。
保留最初 CVE 补丁作历史证据，不逐个反向检查互相覆盖的旧补丁。累计补丁始终以官方 5.6.40 为基线，包含到当前版本的全部修复。
源码完整性检查仅将 NEWS 和两个版本元数据文件与 C/INI 修复分开验证：源代码安全 hunk 不忽略空白、不跳过失败；版本定义另作严格一致性检查。这样合法升版本不会破坏旧版本字符串的补丁检查。

提交累计补丁及配置，经审查合回 `PHP-5.6-security`，再在该分支运行 `release-php56-sec`。最终得到 `php-5.6.40-sec2` 及其完整 Release。
如在 Windows 本机执行命令，可将 python3 换为 python；累计补丁通过字节写入，避免 PowerShell 重定向编码或文本换行转换。

## 仓库设置建议

- 为维护分支启用 PR 审查和状态检查；尽可能让 multi 构建通过再合入。
- 在 Settings → General → Releases 启用 release immutability，冻结已发布的 Tag 和附件。发布工作流按先草稿、上传齐全再发布的顺序兼容该功能。
- 不开启强制更新发布 Tag；不要用同名 Tag 发布不同文件。

参考：https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes

## 本次本地验证与实际发布边界

发布逻辑、版本递增、累计补丁检查、19 包汇总及失败拦截均有本地回归；Windows PowerShell 语法和辅助检查、已有 Linux/Windows Python 回归亦执行。
新发布编排尚需一次实际 GitHub Actions 运行；当前会话没有仓库写入连接，交付包未推送，远端维护分支、Tag、Release 和仓库设置未创建或更改。
