# 树莓派 Zigbee 智能家居方案

> 从 `config-guides` 迁入的历史方案，后续仅在本仓库维护。当前已选择
> Orange Pi Zero 3、SONOFF ZBDongle-E 和 WHDZ04 插座；本文旧硬件建议不代表
> 当前采购清单。现状见 [README](../README.md)，系统候选见
> [Zero 3 选型](./zero3-storage-and-os.md)。

## 目标与推荐结论

在中国大陆，用树莓派本地控制种植用水泵、灯光等电器，按时间或传感器条件执行自动化。不依赖米家、小米／Aqara 网关、品牌账号或云服务，核心控制也不要求 Wi-Fi 路由器或稳定互联网。

开发方式：从 Fedora 开发机通过 SSH 管理树莓派，不需要桌面。当前倾向选择 2GB 内存、Raspberry Pi OS Lite（64 位），用 Rust 编写控制逻辑；实际负载、传感器型号和安全保护仍待确认。

推荐组合：

- **二手树莓派 4B 2GB**：仅运行 Zigbee2MQTT、Mosquitto 足够；加 Home Assistant 做普通智能家居也可用。4GB 版差价小时可选，为后续服务留余量。
- **SONOFF ZBDongle-P USB Zigbee 协调器**：购买带协调器固件的版本。其他协调器也可用，但要核对 Zigbee2MQTT 当前支持列表和固件要求。
- **Aqara 智能插座 T1 国标版，型号 `ZNCZ15LM`**：Zigbee2MQTT 明确支持，具备通断控制、功率／电量监测等功能。下单前核对具体型号、国标插头、适用的 CCC 认证和额定负载。
- **可靠电源与新存储卡**：树莓派 4B 使用可靠的 5.1V / 3A USB-C 电源，配 32GB 或更大的高耐久 microSD 卡；长期大量记录可考虑 USB SSD。
- **USB 延长线**：让 Zigbee 协调器远离树莓派和 USB 3.0 设备，减少无线干扰。

这是选购与架构建议，尚未进行实物配对、负载测试或现场覆盖验证。未比较当前二手报价，不承诺某型号在所有报价下都是性价比最高。

## 连接关系

```text
树莓派：控制程序 + Mosquitto + Zigbee2MQTT
   │ USB
Zigbee 协调器：ZBDongle-P
   │ Zigbee 无线
Aqara T1 国标插座：ZNCZ15LM
   │ 市电输出
220V 电器
```

树莓派可以作为自建 Zigbee 网关的主机，但自带的 Wi-Fi／蓝牙不能代替 Zigbee 无线模块。USB 协调器负责建立 Zigbee 网络，树莓派上的软件负责设备管理和控制。

- Zigbee 控制链路不需要 Wi-Fi 路由器或互联网。
- Mosquitto 和控制程序都在树莓派上时，MQTT 通信走本机，不需要外部网络。
- 首次安装软件、更新系统需要相应的软件获取方式；若要从手机／电脑访问管理页面，需要另行提供以太网、Wi-Fi 等连接。不能把“控制不需要路由器”理解为所有远程访问都自动具备。
- Home Assistant 是可选的；只用程序控制开关时，Zigbee2MQTT + Mosquitto 即可。
- 需要首次安装、配置和配对，不是买来插上就自动可控。

## 系统与开发方式

当前推荐 **Raspberry Pi OS Lite（64 位）+ Zigbee2MQTT + Mosquitto + Rust 控制程序**。

- Lite 是树莓派官方的无桌面通用系统，适合 SSH 管理和自建服务。2GB 内存足够这类轻量控制任务；实际余量取决于日志、历史数据和额外服务。
- Home Assistant OS（HAOS）是专用系统，不是装在 Lite 里的普通应用。将其写入同一张系统卡会替换 Lite 并清空原有数据；使用独立存储卡则可以关机换卡切换，但不是同时运行。
- Home Assistant 不是必需的。需要网页／手机控制、可视化自动化、历史曲线和通知时再考虑引入。
- 保留 Lite 时，可通过 Home Assistant Container 运行 Home Assistant，但没有 HAOS 的应用／附加组件管理；Mosquitto、Zigbee2MQTT 等需要另行部署。
- Home Assistant 可以通过 MQTT 接入 Zigbee2MQTT，也可以用 ZHA 直接管理兼容协调器。**同一个协调器不能同时交给 ZHA 和 Zigbee2MQTT 管理。**

Rust 只需处理业务逻辑，不必自行实现 Zigbee 协议：

| 库／工具 | 用途 |
| --- | --- |
| `rumqttc` | 连接 MQTT，订阅传感器数据、发布控制命令 |
| `tokio` | 异步任务与运行时长计时 |
| `serde` / `serde_json` | 解析 Zigbee2MQTT 的 JSON 消息 |
| `rppal` | 直接操作树莓派 GPIO 时使用；仅控制 Zigbee 设备不需要 |
| `systemd` | 管理开机启动、异常重启和日志 |

可以在 Fedora 写代码，再通过 Git／SSH 传到树莓派编译；也可配置 ARM64 交叉编译工具链，在 Fedora 构建后部署。2GB 足够运行不代表编译大型依赖也很轻松，编译资源应单独考虑。SSH 需要开发机与树莓派之间有可达网络，但不要求互联网。

## Zigbee、MQTT 与两个软件的分工

**Zigbee 负责设备无线通信；MQTT 负责软件之间传递消息。** 两者不是互相替代的协议，也不是都必须连互联网。

| 组件 | 职责 |
| --- | --- |
| USB Zigbee 协调器 | 树莓派进入 Zigbee 网络的无线入口 |
| Zigbee2MQTT | 独立软件：管理配对、适配具体设备，在 Zigbee 与 MQTT 之间双向传递数据和命令 |
| Mosquitto | 独立软件：MQTT Broker，接收发布消息，转发给订阅相应主题的程序 |
| Rust 控制程序 | 根据时间、传感器与安全条件决定是否开泵、开灯 |

Mosquitto 不解析 Zigbee，也不决定何时浇水。它类似消息中转站：Rust 订阅某个传感器的主题，就能收到 Zigbee2MQTT 发布到该主题的数据。

**Zigbee2MQTT 不是单向转换**，项目名称里的 “2” 不限制通信方向：

```text
读数据：传感器 → Zigbee → USB 协调器 → Zigbee2MQTT → MQTT → Mosquitto → Rust
发命令：Rust → MQTT → Mosquitto → Zigbee2MQTT → USB 协调器 → Zigbee → 插座
```

能下发什么命令取决于设备及其适配支持。双向通信不意味着温度传感器可以被“设置温度”，也不保证每个设备都支持主动查询。

MQTT 并非 Zigbee 的强制组成部分；也可以使用其他软件接口直接管理协调器。但选用 Zigbee2MQTT 后，MQTT 就是它与控制程序协作的接口，让设备配对、型号差异和协议处理留给现有软件。

三个软件都运行在树莓派上，Mosquitto 使用本机地址即可。必须区分“消息发布成功”“设备回报状态”和“水泵实际运行”：插座状态反馈也不等于有水流，关键结果可通过水位、流量等独立信号验证。

## 离线运行与时间同步

核心功能按 **离线优先** 设计：日程、配置和必要的执行记录保存在本机；Zigbee2MQTT、Mosquitto 与 Rust 随系统启动，不依赖云账号或在线接口。

| 场景 | 行为与要求 |
| --- | --- |
| 互联网断开，树莓派一直通电 | Zigbee 和本机 MQTT 照常工作；系统时钟继续走，但会逐渐漂移 |
| 互联网恢复 | 网络校时服务自动尝试同步，不要求 Rust 自己实现 NTP |
| 断电重启且没有网 | 需要带备用电池的 RTC，才能可靠恢复日历时间 |
| 开发机无法连接树莓派 | SSH／管理页面不可用，不应影响本机控制 |

树莓派 5B 内置 RTC，可接兼容的备用电池；4B 可加电气兼容、带备用电池的外置 RTC，例如 DS3231 模块。RTC 电池只维持时钟，不能给树莓派或水泵供电；若断电期间也必须控制设备，需要另外设计供电保障。安装 RTC 后应配置并验证开机读取、联网校时及断电保持，不是只接电池就完成验证。

联网不等于已成功校时。使用系统实际配置的网络校时服务，检查其状态；使用 `systemd-timesyncd` 时可通过以下命令检查／启用：

```bash
# 国内使用的时区
sudo timedatectl set-timezone Asia/Shanghai

# 检查网络校时状态
timedatectl status

# 启用系统支持的网络校时服务
sudo timedatectl set-ntp true
```

`System clock synchronized: yes` 表示已同步，但断网期间显示未同步并不自动意味着当前时间不可信。启动时应根据有效 RTC、时间合理性等判断是否允许执行日程，不能把“必须联网校时成功”设为唯一启动条件。网络校时通常足够种植日程使用，不作固定误差或硬实时保证。

控制逻辑应区分两类时间：

- **每天 08:00 浇水**：使用带时区的日历时间。
- **开泵 30 秒后关闭**：使用 `tokio::time`／`std::time::Instant` 等单调计时，避免系统校时跳变改变持续时间；单调计时状态不能跨进程／系统重启直接恢复。

安全规则：

1. 启动后时钟明显异常时不盲目开泵，记录并暴露告警；不要仅凭历史保存时间推断真实断电时长。
2. 保存必要的执行标识／状态，避免重启或时钟回拨导致重复浇水；明确记录与实际动作之间失败时的处理，不能仅靠记录声称保证恰好执行一次。
3. 明确错过日程是跳过还是受限补执行，不自动补跑全部历史任务。
4. 明确传感器数据有效期；设备离线或数据过期时采用安全策略。
5. 开泵后必须有最大运行时长；不能仅安排两个彼此独立的“开启／关闭”定时任务。
6. 程序崩溃、主机断电或无线关泵失败时，软件计时可能失效。保留独立硬件超时、缺水等必要保护，并验证插座断电恢复状态。
7. MQTT 不保留开泵命令，并检查重连队列、消息过期与重试行为，避免恢复连接后执行过时命令。

## 电源、散热与能耗

- 4B 2GB 已能满足当前控制需求。5B 2GB 同样可用，但不必仅为定时与传感器控制购买更高性能主板。
- 5B 建议使用官方 27W USB-C 电源或明确兼容的 5V / 5A 电源；27W 是电源能力，不是主板固定耗电。第三方电源标称 65W／100W 不代表支持所需的 5V / 5A 输出。
- 5B 满载功耗通常高于 4B，轻载差距较小；按实际电源、外设和工作负载测量，不把网上空闲值当作整套系统功耗。平均 5W 连续运行 30 天约耗 3.6 度电，不包含水泵和灯光。
- 普通塑料壳或不接触芯片的金属壳不用涂硅脂。用壳体散热的设计按厂家说明使用导热垫或硅脂；有间隙时不能用硅脂代替指定厚度的导热垫，也不要默认在垫片上叠加硅脂。
- 无风扇运行应选择合适的被动散热方案，结合环境温度实测温度／降频；种植环境还要避免水汽、溅水和冷凝。

## Zigbee 是什么，谁在推动

Zigbee 是低功耗无线通信标准，不是一个插座品牌，也不是小米的私有协议。

- 最初由 **Zigbee Alliance（Zigbee 联盟）**推动，联盟成立于 2002 年。
- 联盟于 2021 年更名为 **CSA（Connectivity Standards Alliance，连接标准联盟）**，继续维护 Zigbee 标准和认证。
- 底层无线通信基于 **IEEE 802.15.4**。
- **Aqara（绿米）**是中国深圳绿米联创的智能家居品牌。品牌背景不意味着其 Zigbee 设备必须通过米家或品牌网关控制。

Zigbee 不是最新的协议，但设备生态和本地控制方案成熟，适合当前需求。Matter 是应用层互通标准；Thread 是基于 IP 的低功耗组网协议。Matter over Thread 是较新的路线，但不应仅因更新就认为一定比 Zigbee 更适合控制插座。

同样标着 Zigbee，也不保证所有功能完全兼容；必须核对具体型号的 Zigbee2MQTT 支持情况。

## 插座如何被识别与配对

1. 插座接通电源。
2. 在 Zigbee2MQTT 中临时开启“允许加入”。
3. 按该型号说明书长按按钮，让插座进入配对模式。
4. 插座加入协调器建立的 Zigbee 网络。
5. Zigbee2MQTT 根据设备地址、厂商／型号及 Zigbee 端点等信息，匹配对应的设备适配规则，暴露开关和监测功能。
6. 给插座命名，例如 `desk_plug`，并关闭“允许加入”。

**配对**解决“加入哪个网络”，**型号适配**解决“软件如何控制它”，两者缺一不可。设备通常会保存网络信息，正常断电重启后自动重连，不必每次配对。

如果设备此前已加入米家／Aqara 网关，需要按说明书复位并重新配对；不能同时加入两个不同的 Zigbee 网络。

## 程序控制示例

假设 MQTT Broker 在本机、设备名称为 `desk_plug`、Zigbee2MQTT 使用默认主题前缀：

```bash
# 开启插座
mosquitto_pub -h localhost -t 'zigbee2mqtt/desk_plug/set' -m '{"state":"ON"}'

# 关闭插座
mosquitto_pub -h localhost -t 'zigbee2mqtt/desk_plug/set' -m '{"state":"OFF"}'

# 观察设备回报，确认实际状态
mosquitto_sub -h localhost -t 'zigbee2mqtt/desk_plug'
```

需要先安装 MQTT 客户端；启用认证时添加相应凭据。发布命令本身不代表插座已执行，程序应观察状态回报并处理离线或超时。

不要为开关命令设置 retained，以免设备重新连接时执行旧命令。Broker 若对外监听，应配置认证和访问控制，不要暴露到公网。

## 二手树莓派怎么选

| 型号 | 建议 |
| --- | --- |
| **4B 2GB** | 首选，满足当前智能家居用途 |
| **4B 4GB** | 差价小时选，为额外服务留余量 |
| 3B／3B+ | 可做简单网关，但只有明显便宜时才值得考虑 |
| 5 | 可用，但当前用途不需要其性能，电源和散热成本更高 |
| Zero 系列 | 简单任务可用，但接口和扩展不如 4B 方便，不作为省心首选 |

购买前检查：

- 要求开机、型号及内存容量截图。
- 确认 USB、网口、Wi-Fi、microSD 卡槽正常，供电口无松动。
- 避免进水、腐蚀和维修板。
- 不为附送的旧卡、杂牌电源或无用配件多付钱；比较单板与整套总成本。

## 220V 安全与投用检查

成品智能插座比裸继电器板更接近“开箱即用”：不需要自行接市电线。微雪等 GPIO 继电器板虽能切换市电，但仍需要正确接线、绝缘外壳和保护措施；市电接线交给合格电工，220V 绝不能接到 GPIO。

投用前确认：

- 电器类型、功率和启动电流。插座标称 10A／16A 或最大瓦数不能直接作为电机、水泵、压缩机等负载的通用能力。
- 插座、电器、墙插的额定能力匹配，不用普通转接头适配不合适的插头或大功率负载。
- 实测开关、状态回报、设备离线以及树莓派重启后的行为。
- 明确并实测停电恢复后插座是保持关闭、恢复旧状态还是其他行为；不要仅相信默认配置。
- 对加热器、水泵等存在风险的设备，保留独立的温控、过载或其他必要保护，不能只依赖无线指令和树莓派软件。

当前尚未确定实际电器及功率，插座是否适合该负载需要在购买前确认。

仅开关插座候选、社区使用反馈与地域规格限制见：[Zigbee 智能插座选购补充](./raspberry-pi-zigbee-plug-research.md)。

## 官方与兼容性参考

- [Zigbee2MQTT 入门与硬件要求](https://www.zigbee2mqtt.io/guide/getting-started/)
- [Zigbee2MQTT 支持的适配器](https://www.zigbee2mqtt.io/guide/adapters/)
- [Aqara ZNCZ15LM 设备支持与功能](https://www.zigbee2mqtt.io/devices/ZNCZ15LM.html)
- [Zigbee2MQTT 支持设备列表](https://www.zigbee2mqtt.io/supported-devices/)
- [Home Assistant 树莓派安装指南](https://www.home-assistant.io/installation/raspberrypi/)
- [Home Assistant Container 安装](https://www.home-assistant.io/installation/linux/)
- [Mosquitto 项目与 MQTT Broker 说明](https://mosquitto.org/)
- [树莓派官方系统配置与 RTC 文档](https://www.raspberrypi.com/documentation/computers/configuration.html)
- [CSA 联盟介绍](https://csa-iot.org/unify/about/)
