# 可复用的本机 Wi-Fi 选择界面

`scripts/select-wifi.py` 在准备系统卡的电脑上扫描附近 Wi-Fi，弹出列表供用户
选择，再通过遮蔽显示的密码窗口收集凭据。不需要在聊天或命令行参数里输入密码。

## 职责与适用范围

- **只选择网络、收集配置**：不烧录、不挂载或修改 TF 卡，不连接所选网络，
  也不切换电脑现有的有线连接。
- 与 Orange Pi / 树莓派型号、目标系统的配置格式无关。消费配置的程序需要
  按目标系统分别生成 Netplan、NetworkManager 或其他受支持的网络配置。
  **不能直接把输出 JSON 复制到卡里，就认为目标设备会读取它。**
- 当前版本运行于带图形桌面、NetworkManager、可用无线网卡的 **Linux 电脑**，
  并不是 Windows / macOS 工具，也不要求在尚未启动的开发板上运行。
- 支持可见、UTF-8 名称的 2.4GHz / 5GHz 家用密码型网络及经确认的开放网络。
  同名、同频段、同安全模式的多个接入点仅显示信号最强者。
- 不支持选择隐藏 SSID、6GHz、WEP、企业 802.1X 或 OWE 网络。WPA3-only 会记录
  `sae` 模式，但目标板的驱动和系统是否支持，仍需实际连接验证。

## 使用

需要 Python **3.10+**、`nmcli` 和 `zenity`，没有第三方 Python 包依赖。
Fedora 的桌面会话内，以普通用户运行：

```bash
sudo dnf install NetworkManager zenity
./scripts/select-wifi.py
```

程序会自动选择唯一的无线网卡，即使电脑当前用有线网络上网，该无线网卡
也可以用于扫描。多张无线网卡时需要明确指定，不会擅自选用其中一张。

```bash
./scripts/select-wifi.py --interface wlp3s0
./scripts/select-wifi.py --band 2.4
./scripts/select-wifi.py --country US
./scripts/select-wifi.py --help
```

`--band` 只过滤选择列表，**不锁定目标设备的连接频段或 BSSID**。
双频网络同名时，目标系统可自行选择连接频段。
无线地区码默认 `CN`；应按目标设备实际使用地点设置。
工具不会自动开启被禁用的无线功能，可先用 `nmcli radio wifi` 检查。

## 输出与凭据安全

成功时标准输出**只有一个文件路径**。文件放在 `$XDG_RUNTIME_DIR`；该变量
未设置时使用系统临时目录。文件名随机生成，权限为 `0600`，仅当前用户可读写。
不要以 `sudo` 或 root 运行此界面。

JSON 格式版本为 `1`，字段如下：

| 字段 | 含义 |
| --- | --- |
| `version` | 格式版本，目前为 `1` |
| `ssid` | 所选 Wi-Fi 的名称，不做去空格等改写 |
| `password` | 用户输入的密码；开放网络为空字符串 |
| `mode` | `psk`：WPA/WPA2 或 WPA2/WPA3 混合；`sae`：WPA3-only；`none`：开放网络 |
| `country` | 无线地区码，例如 `CN` |
| `hidden` | 当前恒为 `false`，此界面只选择可见网络 |

输出文件**包含明文密码**。它不是永久凭据库；调用方负责读取、生成目标系统
配置，并在完成或失败后删除临时文件。不要打印文件内容、提交到 Git 或发到聊天。
仓库额外忽略 `plantctl-wifi-*.json`，但忽略规则不是加密，也不能代替清理。

退出码：成功 `0`；环境、扫描、存储失败 `1`；参数错误 `2`；用户取消 `130`。
取消选择或密码输入不会创建凭据文件。

## 验证

```bash
python3 -m unittest discover -s tests -p 'test_select_wifi.py' -v
uvx ruff check scripts/select-wifi.py tests/test_select_wifi.py
uvx ruff format --check scripts/select-wifi.py tests/test_select_wifi.py
```

CLI 测试使用临时假 `nmcli` / `zenity` 进程，验证选择、频段过滤、密码窗口、
取消、错误恢复、特殊 SSID、文件权限，以及密码不会进入标准输出、错误输出
或外部命令参数。不会扫描真实网络或修改系统。

首次临时版本已在 Fedora 43 上实际扫描、选网、输入密码，并用于写入 Orange Pi
Zero 3 的 Armbian Minimal 系统卡。后续实机启动、Wi-Fi 连接、SSH 与局域网网页
访问均已验证；实际连接频段和树莓派系统适配尚未验证。
