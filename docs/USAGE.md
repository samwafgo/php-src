# PHP 5.6 安全补丁使用指南:Linux / Windows / 宝塔

> 补丁:`patches/php-5.6.40-CVE-2026-109618-109619.patch`
> 打补丁后版本号:**5.6.40-sec1**(PHP_VERSION_ID 不变,仍为 50640)

---

## 〇、动手前的三条铁律

1. **先备份**。无论哪种方式,先把原 PHP 目录/二进制完整备份:

```bash
   cp -a /www/server/php/56 /www/server/php/56.bak        # 宝塔
   cp -a /usr/local/php /usr/local/php.bak                # 常见编译路径
```

2. **configure 参数必须与原安装一致**。查看原来的编译参数:

```bash
   php -i | grep "Configure Command"
   # 或访问 phpinfo() 页面,顶部就有
```

新编译少一个 `--with-xxx`,对应功能直接消失。

---

## 〇.五、💥 出问题怎么还原(先看这节再动手)

**一句话:还原 = 把备份放回去 + 重启服务,全程不超过 1 分钟。**
只要备份在,任何翻车都有救。

### 翻车场景对照表

| 症状 | 原因 | 还原动作 |
|---|---|---|
| 编译中途报错 | 缺依赖/参数废弃 | **什么都没被替换,原 PHP 还在跑,无需还原**;修好编译问题再来 |
| 新 `php -v` 报错、起不来 | 编译机和目标机系统/glibc 不一致 | 换回备份二进制,改在目标机本地编译 |
| 网站 500 / 白屏 / FPM 起不来 | 二进制不兼容 | 换回备份 + 重启 |
| 网站能跑但某功能消失(图片处理没了、连不上数据库) | configure 漏了 `--with-xxx` | 参照"第 0 步"核对参数重编;急的话先还原 |
| 扩展报错 "Unable to load" | 扩展目录变了(prefix 改了) | 把旧扩展目录 `.so` 拷到新目录,或还原 |

### Linux 还原(手动替换方式)

```bash
# 把备份的二进制拷回去
cp /usr/local/php/bin/php.bak /usr/local/php/bin/php
cp /usr/local/php/sbin/php-fpm.bak /usr/local/php/sbin/php-fpm

systemctl restart php-fpm        # mod_php 则 systemctl restart httpd/apache2
php -v                            # 确认回到 5.6.40(不带 -sec1)
```

### Linux 还原(原地编译覆盖方式)

```bash
# 如果你编译前备份了整个目录:
rm -rf /usr/local/php
mv /usr/local/php.bak /usr/local/php
systemctl restart php-fpm
```

### Windows 还原

```
1. 停服务(iisreset /stop 或停 Apache)
2. 把现在的 C:\php 改名为 C:\php-new-bad
3. 把 C:\php.bak 改回 C:\php
4. 启动服务,phpinfo() 确认回到原版本
```

### 宝塔还原

```bash
/etc/init.d/php-fpm-56 stop
rm -rf /www/server/php/56
mv /www/server/php/56.bak /www/server/php/56
/etc/init.d/php-fpm-56 start
# 面板里"重启"PHP 也可以
```

### 还原后的确认

```bash
php -v                            # 回到原版本号
curl -s http://127.0.0.1/ -o /dev/null -w "%{http_code}\n"   # 网站恢复 200
```

> **再强调一次:动手前没备份,出事后谁也救不了。**
> 一条命令的事:`cp -a <php目录> <php目录>.bak`

---

3. **同版本替换核心,扩展不用重编**。补丁不改 PHP_VERSION_ID(50640),
已编译的 `.so` / `.dll` 扩展(mysql、gd、redis……)ABI 兼容,无需动。
但如果你换了 configure 前缀或 ZTS 模式,扩展就得全部重编。

**通用验证**(替换/编译后必做):

```bash
php -v          # 应显示 PHP 5.6.40-sec1
php -m          # 扩展列表与替换前一致
# 重启服务后访问 phpinfo() 页再确认一次
systemctl restart php-fpm      # 或 apache2 / nginx 对应的重载
```

---

## 一、Linux 环境

### 方式 A:自动打包(源码编译,推荐)

适合:自己编译安装的 PHP,或要批量分发给多台机器。

### 第 0 步:提取原配置(小白照做,不用懂参数含义)

**核心思路:你不用"推测",PHP 自己记着当初是怎么编译的,问它就行。**

**① 一条命令拿到原配置:**

```bash
php -i | grep "Configure Command"
```

输出长这样(每台机器不一样,你的一定照抄你自己的):

```javascript
Configure Command =>  ./configure --prefix=/www/server/php/56 --enable-fpm --with-mysql=mysqlnd --with-mysqli=mysqlnd --with-pdo-mysql=mysqlnd --with-gd --with-curl --with-mbstring --with-openssl --with-zlib --enable-zip ...
```

`Configure Command =>` 后面那一整串,就是当年编译时敲的命令,**原样复制下来就是你的编译参数**。

**② 提示 "php: command not found"?说明 php 不在 PATH 里,找它的真身:**

```bash
# 宝塔机器,直接用全路径:
/www/server/php/56/bin/php -i | grep "Configure Command"

# 不知道装哪了,搜:
whereis php
ls /usr/local/php/bin/php /usr/bin/php* /www/server/php/*/bin/php 2>/dev/null
```

**③ 机器上连 PHP 命令行都跑不了?还有两个兜底:**

- 浏览器访问站点的 `phpinfo()` 页面,页面顶部表格里就有 "Configure Command" 一整行;
- 二进制还在但跑不起来的极端情况:`strings /www/server/php/56/bin/php | grep "configure" | head -3`。

**④ 拿到参数后,一键拼出编译命令:**

```bash
# 自动提取并生成(宝塔机器把 php 换成全路径)
php -i | grep "Configure Command" | sed 's/.*Configure Command => *//' > /tmp/old_conf.txt
cat /tmp/old_conf.txt
# 下载源码打补丁后,直接执行:
cd php-5.6.40
eval $(cat /tmp/old_conf.txt)
```

**⑤ 照抄时的三个注意:**

1. `--prefix=...` 是安装路径。想**原地替换**就保持原样(先备份!);想**并存测试**就改成新路径(如 `/usr/local/php56-sec`),验证通过再切换;
2. 参数里可能带 `'`(单引号),复制时一起带上;
3. 极个别十几年前的废弃参数(如 `--with-mysql` 在某些衍生版)如果 configure 报错,**单独删掉报错的那一个**即可,其他不动。

**参数看不懂?没关系,它们就是"装哪些功能"的清单:`--with-gd` 是图片处理、`--with-curl` 是网络请求、`--enable-fpm` 是 FPM 进程管理……照抄 = 功能不变。抄完后 `php -m` 对比扩展列表,就是最终验收。**

### A1. 直接编译安装

```bash
# 1. 下载 5.6.40 正式版源码(官方归档站)
curl -O https://museum.php.net/php5/php-5.6.40.tar.xz
tar xJf php-5.6.40.tar.xz && cd php-5.6.40

# 2. 打补丁
patch -p1 < /path/to/php-5.6.40-CVE-2026-109618-109619.patch

# 3. 用原机器的 Configure Command 编译(这里以常见配置为例)
./configure --prefix=/usr/local/php \
    --enable-fpm --with-mysql --with-mysqli --with-pdo-mysql \
    --with-gd --with-curl --with-mbstring --with-openssl \
    --with-zlib --enable-zip --enable-mbstring
make -j$(nproc)
make test     # 预期:仅 8 例 rfc1867 session 测试失败(见 README)
sudo make install
```

**A2. 打成 deb / rpm 包批量分发**

```bash
# deb(Ubuntu/Debian,用 checkinstall)
sudo apt-get install -y checkinstall
sudo checkinstall --pkgname=php56-sec --pkgversion=5.6.40-sec1 \
    --default make install
# 产出 php56-sec_5.6.40-sec1_amd64.deb,其他机器:
#   sudo dpkg -i php56-sec_5.6.40-sec1_amd64.deb && sudo systemctl restart php-fpm

# rpm(CentOS/RHEL,用 fpm 工具)
gem install fpm
fpm -s dir -t rpm -n php56-sec -v 5.6.40-sec1 /usr/local/php
```

### 方式 B:手动替换二进制(不重编)

适合:线上机器不能停太久、或没有编译环境。**在另一台同系统同版本的机器上编好后,只拷二进制。**

```bash
# 在编译机上完成方式 A 的编译后,需要拷贝的文件:
sapi/cli/php          -> 替换目标机 <php目录>/bin/php
sapi/fpm/php-fpm      -> 替换目标机 <php目录>/sbin/php-fpm
sapi/cgi/php-cgi      -> 替换目标机 <php目录>/bin/php-cgi
# Apache mod_php 场景:
libs/libphp5.so       -> 替换目标机 Apache 模块目录下的 libphp5.so
```

目标机操作:

```bash
# 1. 备份原二进制
cp /usr/local/php/bin/php /usr/local/php/bin/php.bak
cp /usr/local/php/sbin/php-fpm /usr/local/php/sbin/php-fpm.bak

# 2. 拷入新二进制(注意:操作系统版本、glibc 大版本必须与编译机一致,
#    例如都在 CentOS 7 或都在 Debian 12 上编)

# 3. 验证 + 重启
/usr/local/php/bin/php -v        # 5.6.40-sec1
systemctl restart php-fpm        # 或 service httpd restart(mod_php)
```

> 注意:`libphp5.so`(mod_php)是线程模型绑定的——编译时加了
> `--enable-maintainer-zts` 的只能配 Apache event/worker MPM,
> 没加的配 prefork。替换前两边 `httpd -V | grep MPM` 要对上。

---

## 二、Windows 环境

5.6 官方 Windows 包为 **VC11(VS2012 运行库)**,分 4 个包:

| 包 | ZTS | 用于 |
| --- | --- | --- |
| `*-ts-Win32-x86/x64.zip` | 线程安全 | **Apache mod_php**(php5apache2_4.dll) |
| `*-nts-Win32-x86/x64.zip` | 非线程安全 | **IIS FastCGI / NGINX + php-cgi.exe** |

### 方式 A:自动打包(CI)

push 到 GitHub 后,`.github/workflows/build-windows.yml` 产出 4 个 artifact
(首次使用先在一台 Windows 机器上手动跑通,workflow 是草案,见 docs/github-setup.md 第 3 节)。

### 方式 B:手动替换(停站几分钟)

```javascript
1. 确认现有环境:打开 phpinfo() 页,看三项——
   Compiler:   MSVC11 (Visual C++ 2012)     <- 决定运行库
   Architecture: x64 / x86                  <- 决定位数
   Thread Safety: enabled / disabled        <- 决定 TS 还是 NTS

2. 停服务(IIS 用 iisreset /stop;Apache 停服务)

3. 整个目录替换最稳妥:
   把 C:\php 重命名为 C:\php.bak
   解压新包为 C:\php,把 C:\php.bak\php.ini 和 ext\ 下
   你自己后加的扩展(如 php_redis.dll)拷回来

   ——或者只换核心文件:
   NTS: php-cgi.exe、php.exe、php5.dll
   TS : php.exe、php5ts.dll、php5apache2_4.dll(mod_php 场景)

4. 启动服务,访问 phpinfo() 确认版本显示 5.6.40-sec1,
   Thread Safety 状态与原来一致
```

> 若替换后报"无法启动此程序,因为计算机中丢失 MSVCR110.dll":
> 安装对应位数的 Visual C++ 2012 Redistributable。

---

## 三、宝塔面板环境

宝塔的 PHP 在 `/www/server/php/56/`,结构:

```javascript
/www/server/php/56/
├── bin/php              # CLI
├── sbin/php-fpm         # FPM 守护进程
├── etc/php.ini          # 配置
├── etc/php-fpm.conf
└── lib/php/extensions/no-debug-non-zts-20131226/   # 扩展 .so
```

### 方式 A:面板/脚本自动编译(最省心)

1. **先看面板软件商店**:宝塔官方已为本次漏洞发布 7.4/8.0/8.1 打包修复版,
如果 5.6 也出了官方修复包,面板里直接点更新即可,**这是首选,不用本补丁**。
2. 若官方没出 5.6 包,用宝塔自带的编译脚本打补丁重编:

```bash
# 宝塔编译脚本路径(不同版本可能略有差异)
ls /www/server/panel/install/php.sh
# 或直接在面板:软件商店 -> PHP-5.6 -> 设置 -> 编译安装(自定义编译参数)
# 在编译前把补丁内容合入源码:宝塔编译时会解压 /www/server/panel/install/src 下的
# php-5.6.40.tar.gz,可先解压->打补丁->重新打包放回原处,再点面板"编译安装"
```

### 方式 B:手动替换(最快,几分钟)

宝塔的 PHP 也是标准编译产物,按"Linux 手动替换"操作,路径换成宝塔的:

```bash
# 1. 备份
cp -a /www/server/php/56 /www/server/php/56.bak

# 2. 编译机准备(系统版本必须和宝塔机器一致,如都是 CentOS 7):
#    先拿到宝塔机器的编译参数
/www/server/php/56/bin/php -i | grep "Configure Command"
#    在编译机上按方式 A 编译,configure 参数照抄(前缀改为 /www/server/php/56)

# 3. 替换两个核心二进制
scp 编译机:php-5.6.40/sapi/cli/php       root@宝塔机:/www/server/php/56/bin/php
scp 编译机:php-5.6.40/sapi/fpm/php-fpm   root@宝塔机:/www/server/php/56/sbin/php-fpm

# 4. 验证 + 重启(宝塔的 fpm 服务名)
/www/server/php/56/bin/php -v            # 5.6.40-sec1
/etc/init.d/php-fpm-56 restart           # 或在面板里点"重启"
```

> 宝塔机器常见为 CentOS 7(glibc 2.17)或 Ubuntu/Debian。**编译机和宝塔机的
> 发行版、glibc 必须一致**,否则拷过去的二进制起不来。不一致就只能在宝塔机上
> 本地编译(装 gcc: `yum install gcc gcc-c++ make autoconf` 或 `apt install build-essential`)。

### 验证与回滚

```bash
# 验证
/www/server/php/56/bin/php -v                     # 5.6.40-sec1
/www/server/php/56/bin/php -m | wc -l             # 与备份机器一致
curl -s http://127.0.0.1/phpinfo.php | grep -i "5.6.40"   # 站点实际生效

# 回滚(出问题就整目录还原)
rm -rf /www/server/php/56
mv /www/server/php/56.bak /www/server/php/56
/etc/init.d/php-fpm-56 restart
```

---

## 四、补丁生效确认(任意环境通用)

替换/编译完成后,确认两项修复真正生效:

```bash
# 1. OOM 直接终止(不再返回错误页面):CLI 下
php -d memory_limit=2M -r 'str_repeat("a", 50000000); echo "BAD";'
# 预期:输出 Fatal error 到 stderr,进程退出码 1,不会打印 BAD

# 2. upload_progress 已 C 层禁用:Web 下发 multipart 请求带
#    PHP_SESSION_UPLOAD_PROGRESS 字段,检查 $_SESSION 无 upload_progress_* 键
#    (参照 ikow/php2shell-poc 的 poc/verify_session_injection.py)

# 3. 新 INI 存在
php -i | grep max_multipart_body_parts
```