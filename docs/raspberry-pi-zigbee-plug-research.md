# Zigbee 智能插座选购补充

> 从 `config-guides` 迁入的历史选购调研，后续仅在本仓库维护。实际已购插座为
> 文光汇 WHDZ04（`TS011F` / `_TZ3210_cehuw1lw`），配对及计量验证见
> [README](../README.md)。本文候选不代表当前采购清单。

## 范围与结论

针对中国大陆国标插头、树莓派 Zigbee2MQTT 本地控制种植用水泵／灯光。希望仅使用 Zigbee 和开关功能，不为 Wi-Fi、蓝牙或电量统计等非必要功能付费。

当前能明确核对的国标候选是 **Aqara 智能插座 T1，ZNCZ15LM**，但它带电量监测，并非最简功能款。尚未核实淘宝实时价格，也没有足够证据指定一款最低价、无计量、国标且安全可靠的插座。以下不是已完成实物测试的推荐，也不是市场占有率排名。

## 候选与限制

| 候选 | 已核实情况 | 对当前需求的判断 |
| --- | --- | --- |
| Aqara T1 ZNCZ15LM | Zigbee2MQTT 标识为 CN 版，支持开关、功率／电量监测、断电记忆等 [1] | 国标方向的明确候选；若只要开关，需要比较实际价差，不承诺最便宜 |
| IKEA TRETAKT E22x4（E2204／E2214） | Zigbee2MQTT 支持，暴露开关、上电行为等，不暴露电量监测 [2] | 符合简单开关方向，但未确认大陆国标版本／销售；不能把海外推荐直接用于国内购买 |
| Tuya／涂鸦 TS011F 系列 | 例：TS011F_plug_1 带计量；不同固件可能导致不同上报行为 [3] | 涂鸦是平台方案，不是单一品牌质量保证；必须核对具体厂商标识、型号、固件和安全认证，不能只凭 TS011F 购买 |

## 社区通常选什么

Home Assistant 社区中可见 IKEA、SONOFF、NOUS／涂鸦等插座讨论。能证明这些是社区讨论的候选，不能证明“大多数人购买某款”，没有可靠销量／装机比例数据。

- IKEA TRETAKT 有作为开关和 Zigbee 路由器的实际使用讨论，也有特定 Aqara 传感器经它路由时不稳定的反馈；体验不能推广到所有设备组合 [4][5]。
- 社区购买指南讨论中有人反映部分 TS011F／NOUS 插座断连或意外关闭；这是用户报告，不构成所有涂鸦插座都不可靠的证据 [6]。
- SONOFF 海外款必须核对插头和额定电压；S26R2ZB 官方资料列出英规／欧规型号，不据此推荐用于国内国标插头 [7]。

## 淘宝下单检查

1. 明确是 Zigbee 版，不是同链接下的 Wi-Fi／蓝牙 SKU。
2. 要求具体型号、设备厂商标识（例如 `_TZ…`）或 Zigbee2MQTT 配对截图；通用型号可能不足以确定适配。
3. 核对国标插头／插孔、额定电压、适用且可核验的 CCC 认证；不以转接头弥补地域规格差异。
4. 如需省功能成本，询问“无计量／仅开关款”，但按实际成交价比较：无计量并不必然更便宜。
5. 水泵是电机负载，核对电机适用能力和启动电流，不能把阻性负载最大瓦数当作水泵容量。
6. 首先买一个样品，验证本地配对、开关反馈、断电恢复与离线行为，再批量购买；保持独立超时／缺水保护。
7. 软件里的 `on_time` 支持取决于设备固件，不把文档通用说明当作确定的硬件关泵保证 [1]。

## 来源

1. [Aqara ZNCZ15LM 支持与实际暴露功能](https://www.zigbee2mqtt.io/devices/ZNCZ15LM.html)
2. [IKEA TRETAKT E22x4 支持](https://www.zigbee2mqtt.io/devices/E22x4.html)
3. [Tuya TS011F_plug_1 支持与固件注意事项](https://www.zigbee2mqtt.io/devices/TS011F_plug_1.html)
4. [社区：TRETAKT 作为 Zigbee 路由器](https://community.home-assistant.io/t/tretakt-smart-plug-as-a-zigbee-router/723378/7)
5. [社区：TRETAKT 与 Aqara 传感器路由问题](https://community.home-assistant.io/t/ikea-tretakt-plugs-as-zigbee-routers-for-aqara-sensors/766857)
6. [社区：Zigbee buyer's guide，含插座用户讨论](https://community.home-assistant.io/t/zigbee-buyers-guide/654695)
7. [SONOFF 产品说明书列表](https://sonoff.tech/en-us/pages/user-manual)
