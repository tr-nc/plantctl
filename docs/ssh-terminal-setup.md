# 新机器的 SSH 终端初始化

SSH 密钥和登录别名配置好后，还应给远端补齐本机终端的 **terminfo 定义**。
否则用 Kitty 登录精简 Linux 系统时，可能遇到：

```text
tput: unknown terminal "xterm-kitty"
```

## 本次问题与修复

1. **影响范围**：在 Orange Pi 的 `terence` 用户下，`TERM=xterm-kitty tput colors`
   报错并退出 `3`；真正分配 SSH 终端、从客户端传递 `TERM=xterm-kitty` 时也会
   报错。`xterm-256color` 正常。其他用户的状态未验证。
2. **根因**：远端有 `tic`、`infocmp`、`tput`，也装了 `ncurses-term`，但没有
   `xterm-kitty` 的数据库条目。`infocmp -x xterm-kitty` 失败；清除 terminfo 搜索
   路径变量后仍失败。不是 Wi-Fi、内存、SSH 用户名或密钥配置的问题。
3. **何时引入**：在新板子的 Armbian community `26.11.0-trunk.83` 系统上首次使用
   Kitty 时发现。具体上游引入变更及日期未核实，不能把发现时间当作引入时间。
4. **干净修复**：从客户端终端数据库导出完整定义，在远端用 `tic` 编译到当前
   登录用户的 `~/.terminfo`。不篡改 `TERM`，不隐藏 `tput` 错误，不改 SSH 配置。
   实际 SSH 验证已通过：Kitty 返回 `256` 色，列数和清屏能力可读取，原来的
   `xterm-256color` 仍正常。无需重启板子。

## 可复用脚本

在**本机电脑**的项目目录运行：

```bash
./scripts/setup-ssh-terminal.sh orangepizero3 xterm-kitty
```

其他树莓派、Orange Pi 或 Linux 主机只需换 SSH 登录目标：

```bash
./scripts/setup-ssh-terminal.sh user@raspberrypi.local xterm-kitty
./scripts/setup-ssh-terminal.sh another-host
./scripts/setup-ssh-terminal.sh --help
```

不指定终端名称时，使用本机的 `$TERM`。如果初始化时使用 GNOME 终端，之后还要
使用 Kitty，须显式传入 `xterm-kitty`，不能假定当时的 `$TERM` 就是 Kitty。

脚本负责：

- 检查本机是否能导出该终端定义，再建立 SSH 连接。
- 保留扩展能力并在目标机编译，适用于本机 x86_64、远端 ARM64 等不同架构。
- 只写远端**当前登录用户**的 `~/.terminfo`，保留其他终端定义，可重复执行。
- 用 `infocmp` 和 `tput` 的正常数据库查找路径验证结果，不靠临时搜索路径覆盖
  掩盖问题。临时源文件退出时删除。
- 使用正常 SSH 身份认证与主机密钥检查，不保存密码，不安装系统包、不要求 sudo。

需要本机 `ssh`、`infocmp`，远端 `tic`、`infocmp`、`tput`；缺少远端工具时，
Debian / Ubuntu 可由管理员安装 `ncurses-bin`。本机若没有对应终端定义，应先
安装本机终端的软件或其 terminfo 包。当前脚本针对支持从 `/dev/stdin` 读取定义
的 ncurses/Linux 目标；macOS、传统 termcap 系统不是已验证目标。

终端程序有时提供 `TERMINFO` 指向其自带数据库，脚本会使用它导出本机定义。
**不要为了复制定义而清除客户端的 `TERMINFO`。** 客户端搜索路径不需要上传；
安装后远端会按当前用户的默认数据库位置查找。

`tic` 对某些终端条目的名称/别名格式可能给出提示；是否成功以编译退出码和随后
的实际查询验证为准，不是通过吞掉错误判断成功。

### root / sudo 的范围

此脚本不声称为所有用户完成修复。另一个登录用户需要对其 SSH 目标单独执行。
如果在 `sudo` / `su` 后仍遇到未知终端，管理员可安装系统级 **`kitty-terminfo`**
包；用户级 `~/.terminfo` 不保证 root 的搜索路径能够读取。仅安装 `ncurses-term`
并不能保证有 Kitty 的定义，本次机器就已安装该包但仍缺条目。

## 配置新机器的顺序

1. 烧录该板型对应的系统，并按目标系统配置 Wi-Fi。
2. 完成首次登录、修改初始密码、创建普通用户。
3. 用 OpenSSH 的 `ssh-copy-id` 授权本机公钥，为该机器设置独立 SSH 别名。
4. 运行本页的终端初始化脚本。
5. 用 SSH 检查内存、磁盘扩容、时间和网络，再部署业务软件。

终端初始化与 Wi-Fi 配置、烧录格式无关，可作为这些流程中的独立步骤复用。

## 验证

```bash
bash -n scripts/setup-ssh-terminal.sh
python3 -m unittest discover -s tests -p 'test_setup_ssh_terminal.py' -v
ssh orangepizero3 'TERM=xterm-kitty tput colors'
TERM=xterm-kitty ssh -tt orangepizero3 'tput colors'
```

自动测试用本机真实 ncurses 工具编译和查询数据库，只有 SSH 传输被替换成临时
本地目标。覆盖 Kitty、普通终端、保留已有条目、重复执行、失败清理及参数注入防护。
实际 Orange Pi 的 ARM64 编译及 SSH 终端行为也已验证；其他板型仍需现场确认。

参考：[Kitty 官方手动复制 terminfo 说明](https://sw.kovidgoyal.net/kitty/kittens/ssh/#manual-terminfo-copy)。
