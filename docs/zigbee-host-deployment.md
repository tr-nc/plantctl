# Orange Pi Zigbee 网关部署与局域网管理

## 当前交付状态

**已完成实机安装、原网络迁移、网页登录、实时设备查询和正常重启后的自启验证。**
Orange Pi 负责运行服务；Fedora 只是管理网页的客户端，不再承担 MQTT 或 Zigbee 网关。

| 组件 | 实际部署 |
| --- | --- |
| 主机 | Orange Pi Zero 3 / Armbian Debian 13 Minimal / ARM64 |
| MQTT Broker | Debian Mosquitto **2.0.21**，原生 systemd 服务 |
| Zigbee2MQTT | **2.14.2** 官方 ARM64 镜像，Podman **5.4.2** + 系统级 Quadlet |
| 协调器 | 原 SONOFF Dongle-E / `ember` / EmberZNet **7.4.4**，未刷固件 |
| 已配对设备 | 保留 `plant-light` / `TS011F_plug_1`，无需重新配对 |
| 网页 | <http://192.168.50.101:8080> |
| 主机名网址 | <http://orangepizero3.lan:8080>，已在 Fedora 验证 DNS 和 HTTP |
| MQTT | **仅** `127.0.0.1:1883`，没有对局域网发布 |

浏览器显示 **Auth → Token** 时，输入安装时在本地遮蔽窗口设置的**网页访问密码**。
没有额外的网页用户名；它不是 SSH 用户密码或 Wi-Fi 密码。密码不记录在本文。

网页可以管理配对、查看数据、操作支持的设备。无须给小机器安装图形桌面，
也无须持续开着 SSH 或 Fedora。路由器与小机器仍须供电，浏览器客户端须能到达
允许的局域网；关闭管理页面不停止网关。

**未包含 Rust 自动化控制器、浇水日程、最大运行时长保护或 Home Assistant。**
不能把本次交付理解为自动浇水已经投用。未进行危险负载、插座断电恢复或长期稳定性测试。

## 所有权、安全与持久化

- `mosquitto.service`、`plantctl-lan-guard.service`、`plantctl-zigbee2mqtt.service`
  由小机器的系统 systemd 管理，而不是 Fedora 容器、SSH 会话或登录用户会话。
- Zigbee2MQTT 是非 root 的 `plantctl-zigbee` 用户运行的容器，额外拥有设备所需的
  串口组。未设置 `--privileged`，未把设备改为 `chmod 777`。
- 容器根文件系统只读，移除 Linux capabilities，启用 no-new-privileges；
  只挂载必要的设备、应用数据和只读 udev 信息。当前内存限额 512MiB，Node
  堆上限 256MiB；不是对未来任意设备数量的性能保证。
- 镜像在安装时解析并固定到 digest，`Pull=never`；开机不会重新下载镜像或依赖
  Fedora 提供文件。没有配置自动更新或固件升级。
- 网页监听 IPv4 `0.0.0.0:8080`，专用 nftables 表只允许 `127.0.0.1` 和当前
  **`192.168.50.0/24`** 来源，拒绝其他来源访问此端口。规则不修改 SSH 端口，
  不清空其他应用的防火墙表；网关在防火墙服务成功后才启动。
- 网页还需要 Token 鉴权。HTTP 没有 TLS，仅适合信任的家庭局域网；**不要做
  公网端口映射**。改变 LAN 子网或网页端口时，要一起审核监听与防火墙配置。
- MQTT 匿名访问仅用于本机进程，不开放到 LAN。应用配置使用
  `mqtt://127.0.0.1:1883`，不是 Fedora 的地址。
- 当前配对入口已关闭：`permit_join: false`（桥接状态报告）。以后配对时只临时
  开启 Permit join，结束后关闭。

关键路径：

```text
/var/lib/plantctl/zigbee2mqtt/                       # 网络、设备、配置及协调器备份
/etc/containers/systemd/plantctl-zigbee2mqtt.container
/etc/mosquitto/conf.d/plantctl-local.conf
/etc/systemd/system/plantctl-lan-guard.service
/etc/plantctl/zigbee-lan.nft
/etc/plantctl/zigbee-host.owner
```

应用数据目录权限 `0700`，迁入文件 `0600`，归专用服务用户所有；管理备份需要 sudo。
配置中存在明文网页 Token 和 Zigbee 网络密钥，**不可打印、提交 Git 或上传公开日志**。
运行日志使用 journal，避免同时向应用目录重复写一份文件日志。

主机串口使用 `/dev/serial/by-id/` 固定设备路径，映射到容器 `/dev/ttyUSB0`。
不用裸的主机 `ttyUSB0` 编号识别硬件；启动时重新解析固定路径。

## 已完成的闭环验证

1. Fedora 源容器已停止；完整源数据备份在私有、Git 忽略的
   `.local/backups/zigbee-fedora-before-host-migration-*.tar.gz`，原始数据也保留。
2. 完整迁移 `configuration.yaml`、`database.db`、`coordinator_backup.json`、
   `state.json` 和其他数据文件；只修改目标串口、目标 MQTT、网页及日志配置。
3. 启动后和重启后比较网络 key、PAN ID、扩展 PAN ID、channel 和设备配置，
   确认保留；比较时只输出布尔结果，没有输出密钥。
4. MQTT 桥接状态为 `online`；桥接元数据确认版本 2.14.2 / 固件 7.4.4，设备列表
   含原来的 `plant-light`，interview 已完成。
5. Fedora 经 LAN 直接访问 IP 和主机名网址均返回 HTTP 200；真实浏览器用 Token
   登录并看到设备的 Exposes 页面及 ON/OFF 控件。
6. 未鉴权 WebSocket 收到 **4401 Unauthorized**，没有收到受保护的数据。
   注意：服务先升级 WebSocket，再执行 Token 检查；不能把 `onopen` 本身误判成
   已通过授权。
7. 从 Fedora 连接主机 1883 失败，确认 MQTT 未暴露到 LAN；实际 socket 测试中
   允许来源 127.0.0.1 可访问网页，不允许来源 127.0.0.2 被阻断。
   未另取一个外部 VLAN/公网主机做跨网段实测。
8. 用不保留的 `/get` 请求只读查询插座，订阅时跳过 retained 缓存，收到新鲜的
   状态/电压/功率回报。**没有发送 ON/OFF 指令，也没有给设备重新配对。**
9. 执行一次正常主机重启，检查 boot ID 已改变；没有运行启动命令，三项服务
   自行恢复，网页与实时 Zigbee 查询再次通过。Fedora 本地 Podman 容器全程停止。
10. 重新应用安装器时，现有网络、设备及网页密码未覆盖，使用本地已缓存镜像，
    网关再次上线。重启后的初始观察约使用 208MiB RAM、可用约 1.2GiB，未使用 swap；
    这不是长期运行或高负载测试。

实际将 Fedora 关机的实验未做，以免终止当前管理会话；独立运行依据是小机器上的
系统服务、所有依赖均在本机，以及 Fedora 服务停止时仍成功收到实时设备回报。

Podman 5.4 Quadlet 默认添加 `network-online.target` 排序。冷启动时可能等待系统
的网络上线流程；持续运行后的 Zigbee/MQTT 不以 Fedora 或互联网为依赖。本次
未验证路由器断电情况下的冷启动等待时间，也未验证无网断电后的日历时间可靠性。

安装所需 Debian 软件源正常获取包；重复检查时 **Armbian beta 镜像连接失败**，
APT 复用了该源旧索引。未修改这个源、未升级内核；不影响上述已安装服务，但不能
宣称所有 OS 软件源均已更新，后续系统维护应另行检查。

## 日常管理

Fedora 浏览器打开上方网址即可。SSH 查看服务：

```bash
ssh orange-pi-zero-3 'systemctl is-active mosquitto plantctl-lan-guard plantctl-zigbee2mqtt'
ssh orange-pi-zero-3 'journalctl -u plantctl-zigbee2mqtt -n 50 --no-pager'
```

需要主动重启网关时：

```bash
ssh -t orange-pi-zero-3 'sudo systemctl restart plantctl-zigbee2mqtt'
```

若需连同 Broker 重启，显式重启两者，不依赖单独重启依赖服务来恢复网关：

```bash
ssh -t orange-pi-zero-3 'sudo systemctl restart mosquitto plantctl-zigbee2mqtt'
```

Quadlet 生成的服务显示 `UnitFileState=generated`，由源文件 `[Install]` 自动加入
开机目标；不要对生成的 service 执行 `systemctl enable`。Mosquitto 和防火墙服务
是普通 enabled 服务。异常退出会按 Restart 策略重试，主动 stop 则尊重管理员意图；
这不是所有硬件故障均能自动恢复的保证。

保留网关数据和备份；做一致性备份时先暂停网关，再私密打包应用目录并恢复服务。
暂停网关不会自动关闭插座，重要负载须事先进入安全状态。不要随意删除网络 key、
数据库或协调器备份，也不要同时让另一个程序使用协调器。

地址仍由 DHCP 分配，不保证永久为 `.101`。主机名依赖路由器的本地 DNS；若需要
长期固定 IP，应在路由器给本板做 DHCP 地址保留，而不是随便占用一个静态地址。

## 可复用安装材料

- `scripts/prepare-zigbee-host.py`：准备完整数据副本，保留原网络和源文件；
  拒绝缺失/GENERATE 网络标识、缺数据库/备份、覆盖现有目的地、不私密的认证文件
  或 staging 父目录。需要 Python 3.10+ / PyYAML，支持 `uv run` 的脚本依赖声明。
- `scripts/install-zigbee-host.sh`：在 **Debian 13** 上用 sudo 执行，安装主机服务、
  固定镜像和 LAN 防火墙；拒绝占用不明的应用路径、已有非本任务 Mosquitto 或容器，
  不覆盖现有网络数据。旧 Debian/其他 OS 需审核适配，不假定包版本和 Quadlet 通用。
- `tests/test_prepare_zigbee_host.py`：通过 CLI 和数据文件检验迁移、权限、兼容输入、
  失败拒绝及敏感信息不进入输出。

```bash
./scripts/prepare-zigbee-host.py --help
./scripts/install-zigbee-host.sh --help
# Auth JSON 是临时、当前用户专属的 0600 文件，只需包含 frontend_password。
# 用本地遮蔽输入创建它，不把真实密码放在命令参数或此处的示例中。
./scripts/prepare-zigbee-host.py OLD_DATA PRIVATE_STAGE/data --auth-file PRIVATE_AUTH_JSON
# 将 data 和安装脚本私密传给目标，再在目标执行：
sudo bash install-zigbee-host.sh PRIVATE_STAGE/data ghcr.io/koenkk/zigbee2mqtt:2.14.2 192.168.50.0/24
```

准备前停止源实例、私密备份，检查 `.local/` 忽略规则。验证成功后清理本地/远端
临时 staging、认证文件和一次性密码收集/授权程序。正式应用配置及恢复备份须保留。

开发验证（非系统 Python 可通过 uv 获取 PyYAML）：

```bash
uv run --with 'PyYAML>=6,<7' python -m unittest discover -s tests -p 'test_*.py' -v
uvx ruff check scripts/prepare-zigbee-host.py tests/test_prepare_zigbee_host.py
uvx ruff format --check scripts/prepare-zigbee-host.py tests/test_prepare_zigbee_host.py
uvx --with PyYAML --with types-PyYAML pyright scripts/prepare-zigbee-host.py tests/test_prepare_zigbee_host.py
bash -n scripts/install-zigbee-host.sh
```

## 官方依据

- [Zigbee2MQTT：迁移到另一运行环境](https://www.zigbee2mqtt.io/guide/faq/#how-do-i-move-my-zigbee2mqtt-instance-to-a-different-environment)：同一协调器迁移主机时复制完整 data 并更新串口路径，不换网络身份。
- [官方容器安装](https://www.zigbee2mqtt.io/guide/installation/02_docker.html)：ARM64 镜像、数据挂载、固定串口及非 root 串口组权限。
- [网页设置与 Token](https://www.zigbee2mqtt.io/guide/configuration/frontend.html)：监听地址、端口及鉴权配置。
- [Podman 5.4 Quadlet](https://docs.podman.io/en/v5.4.2/markdown/podman-systemd.unit.5.html)：系统服务生成、`[Install]`、设备/用户映射、Pull、重启策略及依赖。
