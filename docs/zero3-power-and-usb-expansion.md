# Orange Pi Zero 3：电源、开关机与 USB 扩展调研

## 结论

- **不能证明 Zero 3 的电源芯片比 Raspberry Pi 5 更可靠。** 两者型号、负载与
  电源设计不同；本次没有获得可比较的故障率、受控测试或原帖的明确失效分析。
- 正常关机应先执行 `sudo poweroff`，关机完成后才拔电。Zero 3 标准板没有
  Raspberry Pi 5 那样的板载电源按钮；接通电源会启动，关机后再次开机按厂商
  方法重新接通电源。[1]
- 不需要因为只有一个 USB-A 就先买扩展坞。当前方案只需要一个 Zigbee 协调器，
  优先 USB 延长线；确实有第二个 USB 外设时再选择 Hub 或 13pin 扩展板。[1][6][7]

本次只读取板子状态，没有执行关机、拔电实验、USB 带载实验或电源可靠性测试。

## 1. 电源管理芯片的已确认信息

通过本机 `ssh orangepizero3` 读取运行中的设备树和 I2C 驱动信息：

```text
/sys/firmware/devicetree/base/soc/i2c@7081400/pmic@36
/sys/bus/i2c/devices/0-0036/name: axp313a
```

Linux 上游的 Zero 3 设备树也将此节点标为 `x-powers,axp313a`，并描述 CPU、
GPU、内存、1.8V 与 3.3V 供电。因此本板软件识别的 PMIC 为 **AXP313A**；本次
没有拆板读取芯片丝印。[2]

Raspberry Pi 官方介绍明确说明 Pi 5 使用 Renesas **DA9091**，为 BCM2712 和
RP1 供电，集成多路开关电源、RTC 和 PC 式电源按钮功能。[3]

| 比较项 | 本次 Zero 3 | Raspberry Pi 5 |
| --- | --- | --- |
| PMIC | 驱动/设备树识别为 AXP313A | 官方说明为 DA9091 |
| 电源建议 | 厂商手册列出可靠的 5V/2A 或 5V/3A USB-C 电源；本项目建议 5V/3A 留余量 | 不应直接套用 Zero 3 的供电要求；按 Pi 5 及外设要求选择电源 |
| 是否更耐异常断电 | 未建立比较证据 | 未建立比较证据 |

芯片更简单、功耗需求较低或价格不同，都不能直接推出故障率更低。对于本项目，
重点是可靠的 **5V** 电源、线材、避免短路/过压/倒灌，以及正常关机。厂商手册
明确警告不要向 Zero 3 输入高于 5V 的电源，并指出反复重启可能来自电源或线材。[1]

## 2. “直接拔电会烧坏 Pi 5 PMIC”是否已证实

要区分两个问题：

1. **文件系统/数据损坏**：Zero 3 手册 §3.36 明确指出，运行中直接拔电可能导致
   文件系统数据丢失，建议先 `poweroff`。这是有来源支持的日常操作风险。[1]
2. **硬件故障**：PMIC 过热、无法开机、供电轨异常或 I2C 错误，需要另行诊断。
   仅有“断电之后开不了机”这个顺序，不能证明拔电烧坏了 PMIC。

找到的 Raspberry Pi 官方论坛个案 **Two RPi 5 dead** 描述两块 Pi 5 无法启动，
包括电源芯片附近发热，以及另一块出现三长三短的指示灯错误。作者讨论了电源
启动瞬态，并承认无法完全排除电源异常；这些叙述本身没有确证“正常拔电导致
PMIC 损坏”，也不是板型总体故障率统计。[4]

另有 Pi 5 用户讨论有源 USB Hub 是否反向供电：其 USB-C 输入功率在接 Hub 后
下降，被作者解释为回灌。它是应重视的个案讨论，**不是已确认的 PMIC 损坏
因果链，也不是本板实测**。[5]

用户记忆中的原帖尚未提供，无法确认它具体讲的是哪种故障、哪个硬件版本或
哪种供电接法；不能据此认定 Pi 5 的 PMIC“特别差”，也不能保证 AXP313A 更好。
论坛部分页面直接读取受到 403 限制；上述案例使用搜索服务返回的原帖索引文本，
不是对全部回复或厂商售后结论的完整核验。

## 3. 本板开关机操作

厂商手册 §2.7 描述插卡、接电并打开电源适配器开关即可启动；§3.36 说明关机后
需重新接通电源才能再次开机。标准板正反面接口图没有 PC 式板载电源按钮。[1]
本机此前插卡通电后成功启动、连上 Wi-Fi，也是一次实际验证。

在 Fedora 上，用户主动决定关机时运行：

```bash
ssh -t orangepizero3 'sudo poweroff'
```

`-t` 为 sudo 提供交互终端；如需验证，输入板子上 `terence` 用户的登录密码，
而不是 Wi-Fi 密码。**这条命令确实会关机，不要拿它做无意的连通性测试。**

等待系统关机完成再拔电。SSH 断开不等于所有服务和写盘立即完成，不应把固定
等待秒数或某一盏 LED 的状态当作对所有系统的保证；当前 Armbian 镜像关机时的
灯态和实际耗时尚未现场测量。观察串口/显示器的关机完成信息是更明确的依据。

仅重启系统则使用：

```bash
ssh -t orangepizero3 'sudo reboot'
```

以后连了水泵或灯，须先让负载进入安全状态并确认。**关掉主机不等于 Zigbee
插座自动断电**，不能把关板子当作可靠的关泵手段。

## 4. USB 扩展方式与社区使用

### 硬件能力

厂商手册 §1.4、§2.10 和 §3.15 明确列出 **3 路 USB 2.0 Host**：
一只现成 USB-A 接口，另外两路从 13pin 接口引出；兼容扩展板增加两只 USB
接口。[1]

本板 `lsusb -t` 观察到三组 EHCI/OHCI 根控制器（480M / 12M），与这些 USB 2.0
主机能力相符；这不等于六只物理 USB 插口，也不能代替扩展板实插测试。

| 方案 | 适合场景 | 注意事项 |
| --- | --- | --- |
| 原 USB-A + 延长线 | 只有一只 Zigbee 协调器 | 本项目当前首选，不需要 Hub |
| USB-A 外接 Hub | 多只 USB 外设，希望少改机械结构 | 共用该上行口；高速 Hub 不会把本板升级成 USB 3.0 |
| Zero 3 兼容 13pin 扩展板 | 希望引出另外两路原生 USB Host | 核对方向、Zero 3 兼容性及机壳空间；不是给原 USB-A 串接一个 Hub |

13pin 扩展板即使带麦克风，该麦克风功能在 Zero 3 上也不受支持，厂商手册对此
专门提示；不要把其他 Orange Pi 的全部扩展功能套过来。[1]

USB-C 在手册接口图中标为电源输入，另有 Android ADB 的 USB 设备模式说明。
**不要把普通电脑 USB-C 多功能扩展坞默认视为可用的 USB Host 扩展方案**；本次
未验证 Type-C Hub/PD 扩展坞兼容性，推荐从 USB-A 或指定 13pin 板扩展。

### 其他人是否“都会用扩展坞”

没有代表性统计，不能说所有人或大多数人都会扩展。我读到的一个同型号实践
案例是将 SONOFF Dongle-P 直接接到 Zero 3 并用于 Home Assistant，说明单协调器
用途并非必须加 Hub。它是个人实作记录，不是我们的 Dongle-E/当前 Armbian 的
兼容性测试，也不建议照搬其容器权限设置。[6]

论坛搜索出现了 Hub 和扩展板讨论，但部分原帖未能完整读取，且有搜索结果
实际上属于 **Radxa Zero 3** 或其他 Orange Pi 型号；这些不能当作本板实证。
本次扩展板的确定依据是厂商手册，不是跨型号社区猜测。

### 对本项目的建议

**用户实物确认的机械限制**：SONOFF Dongle-E 直接插入本板 USB-A 时，其外壳/
插头空间与相邻 USB-C 供电插头干涉，无法同时正常插到位。这是当前硬件组合的
物理尺寸问题，不是 SSH、USB 驱动或 PMIC 配置造成的。连接时不要硬挤，避免
顶松供电插头；推荐用 **窄头、软线的 USB-A 公转 USB-A 母数据延长线**隔开。
具体延长线与现有电源插头的同时插入间隙仍需实物确认。仅为解决这一干涉，
没有必要购买 Hub；Hub 自身的上行插头也需检查尺寸。

- 当前只连接 SONOFF Dongle-E 时，先使用约 **0.5–1m 的 USB 延长线**，让协调器
  离开主板及其他无线/高速设备。Zigbee2MQTT 官方指南认为 50cm 已有帮助，并
  提醒附近 USB、HDMI、SSD 和无线设备可能干扰 Zigbee。[7]
- 若之后增加硬盘、摄像头等外设，再评估有独立电源、明确不向主机上行口倒灌
  的 Hub；板子仍由自己的合适电源供电。不把未知 Hub 当作主机的供电来源。
- 非标准 Hub 的反向供电可能让拔掉 USB-C 后板子仍被另一条路径供电，或引入
  额外供电接法风险。采购应要求上行端无反向供电，不按“有源”两个字直接认为
  安全。[5][8]
- 本次没有选定或测量任何具体 Hub；也没有验证所选 3D 打印机壳是否容纳 13pin
  扩展板。扩展前先确认机壳空间与线缆布局。

## 来源

1. [Orange Pi Zero 3 H618 用户手册 v1.1，厂商撰写、经销商镜像](https://orangepi.net/wp-content/uploads/2023/10/OrangePi_Zero3_H618_user-manual_v1.1.pdf)：重点 §1.4、§1.6、§2.1、§2.7、§2.10、§3.15、§3.36；已下载阅读对应章节及正反面接口图。
2. [Linux 上游 Zero 3 设备树](https://raw.githubusercontent.com/torvalds/linux/master/arch/arm64/boot/dts/allwinner/sun50i-h618-orangepi-zero3.dts)：`pmic@36` 与 `x-powers,axp313a`；与本机只读驱动检查相符。
3. [Raspberry Pi 官方：Introducing Raspberry Pi 5](https://www.raspberrypi.com/news/introducing-raspberry-pi-5/)：DA9091 节；已读取正文。
4. [官方论坛用户个案：Two RPi 5 dead](https://forums.raspberrypi.com/viewtopic.php?t=374141)：读取了搜索索引原帖内容，未完整核验全部回复及最终失效结论。
5. [官方论坛用户讨论：Is Pi5 Partial USB Back-Powering Bad?](https://forums.raspberrypi.com/viewtopic.php?t=361704)：搜索索引中作者的测量描述，不作为已证实的硬件失效因果链。
6. [作者实作：Zero 3 接 SONOFF Dongle-P](https://juantechblog.github.io/posts/integrate-sonoff-zigbee-dongle-plus-p-into-home-assistant/)：已读取正文及图注；仅说明这种无 Hub 用法存在。
7. [Zigbee2MQTT：Improve network range and stability](https://www.zigbee2mqtt.io/advanced/zigbee/02_improve_network_range_and_stability.html)：USB 延长线、设备间距与无线干扰建议；已读取正文。
8. [USB Back Voltage 合规测试说明](https://testusb.com/backvoltage_issue.htm)：引用 USB 2.0 上行端不应向 VBUS 供电的要求；本次使用搜索索引摘录，未对具体 Hub 做电气合规测试。
