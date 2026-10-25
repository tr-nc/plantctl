# Plantctl 局域网控制页

## 访问

- 无线：<http://192.168.50.102/>
- 有线接通时：<http://192.168.50.101/>
- 原 Zigbee2MQTT 管理页保留在 `:8080`，配对和高级设置仍在那里操作。

无需 HTTPS 证书。手机或电脑须能访问 `192.168.50.0/24` 局域网；访客 Wi-Fi 的客户端隔离可能阻止访问。
日常控制页打开即自动连接，不要求密码。按用户选择，以局域网访问权作为授权：同网段的无线、有线设备均可控制。
原 `:8080` 高级管理页面仍保留密码，但免登录代理可访问同一网关 API，不能将高级页面的密码理解为对可信 LAN 客户端的独立权限隔离。
HTTP 不加密，仅适用于可信局域网，禁止公网端口映射。页面所有素材本地提供，没有 CDN、外部字体或云服务依赖。

## 当前范围

- 为现有的 `plant-light` 提供状态、功率、电压、累计用电和 ON/OFF 操作。
- 深色、精简布局，只保留设备、读数、开关及必要连接反馈；适配手机。
- 没有刷新按钮或“已更新”时间。正常状态安静显示，后台自动查询并接收设备上报；无新鲜状态、断线或操作未确认时才显示异常提示。
- 发出开关请求不立即改写显示状态；收到匹配状态报告才确认。超时、断线显示结果未确认，不自动重发控制指令。
- 左侧图示按设备最近上报状态更新：ON 亮灯并显示光束，OFF 灭灯变暗；网关断开、无状态时使用中性灰色图示。点击按钮不会乐观切换图示。
- 提供每日自动开关，后台独立运行；关闭网页或停止网页服务不停止定时任务。
- 不包含节假日、历史图表、多设备管理或安全浇水逻辑。

## 每日自动开关

- 初次安装默认关闭，预填开启 `08:00`、关闭 `22:00`。24 小时圆环顶部为 00、右侧 06、底部 12、左侧 18；亮色弧表示亮灯时段，中央显示时长。
- 拖动“开/关”端点按半小时吸附；也可选择下方开启/关闭时间卡片，再点按圆环定位，不需要打字。键盘方向键调整半小时，Home/End 定位 00:00/23:30；端点不允许重合。
- 调整仅修改草稿，点保存才生效；切换“自动开关”会立即保存当前草稿及开关状态。取消触摸手势会还原本次拖动前的值。
- 旧 HH:MM 配置仍可读取且不静默取整，调整对应端点时才吸附。设计依据见 [圆环交互调研](schedule-dial-research.md)。
- 固定使用 **Asia/Shanghai（北京时间）**，不依赖手机时区或主机 UTC 显示。每日重复，支持 `20:00 → 06:00` 之类的跨午夜时段，开关时间不能相同。
- 开启时间包含在亮灯时段内，关闭时间起熄灯。启用、修改规则或调度服务重启后，按当前时段执行一次；停止自动模式不额外开关灯。
- 手动操作维持到下一次定时边界。服务不会每秒强制覆盖手动操作。重新启用、改规则、重启调度服务会重新按规则对齐。
- 断网期间不堆积开关命令；网关恢复后只补当前时段，不重播已错过的多个动作。同一时段内正常重连不覆盖手动状态。
- 等待本次启动的系统校时成功后才执行（systemd-timesyncd 标记），避免掉电后错误时钟触发定时。校时尚未完成会显示提示。
- 每秒检查时间边界，不承诺硬实时。MQTT 指令不保留、不持久排队；成功提交不等于物理设备已执行。插座离线或无线丢包仍可能导致动作未执行，不自动重发已提交指令；以设备实际回报为准。这不是安全联锁或浇水保护器。
- 配置先原子写入并 fsync，再激活；版本号拒绝其他浏览器的过期覆盖。关闭自动模式后，不会再派发新的定时指令；已经提交给网关的指令无法撤回。

## 架构与部署

`web/` 是无构建依赖的 HTML/CSS/JavaScript 页面。专用 nginx 实例在 IPv4 80 端口提供静态资源，
同源 `/api` WebSocket 代理到现有 `127.0.0.1:8080/api`。安装器从已有网关配置读取 Token，
生成 root 所有、0600 权限的 `/etc/plantctl/web-upstream.conf`。systemd 的 LoadCredential 将其提供给专用 nginx 实例，
由代理附加上游 Token，浏览器无需输入或保存凭证；不会修改原网关配置或 Zigbee 密钥。
更换高级管理密码后须重新运行安装器以更新代理凭证。
只有收到网关数据才启用控制按钮，不能把 WebSocket 升级成功视为网关已就绪。

nginx 允许 `127.0.0.1` 和 `192.168.50.0/24`，其他来源返回 403；API 要求同源 Origin。
Host 白名单限 `.101`、`.102`、回环地址、localhost 和 orangepizero3.lan/local，拒绝任意主机名及 DNS rebinding 来源。
不开放 MQTT，不修改原网关或原防火墙。关闭访问日志和 API 错误日志以避免记录查询参数中的 Token。
静态资源使用 CSP、禁止嵌入、无缓存等响应头。服务使用 DynamicUser、只读系统及受限绑定端口能力。

`controller/` 是 Python 后台，由独立 `plantctl-scheduler.service` 管理。通过 Paho MQTT 2.x 连接本地 Broker，
API 只监听 `127.0.0.1:8091`，由 nginx 代理 `/schedule` 和只读 `/device-status`。对 `/schedule`，`GET` 查询，`PUT` 保存完整
`{enabled, on, off, revision}`；写请求必须同源，非 JSON、非法时间返回 400/415，版本冲突返回 409。
调度与配置修改在同一锁内串行化，后台主线程负责派发；异常退出由 systemd 重启，不会留下仅 API 存活的假正常服务。
配置文件异常时拒绝启动，不能静默恢复默认并覆盖用户设置。

设备状态由后台 `MQTTGateway` 统一管理：网关恢复后立即查询，之后每 30 秒发一次不保留的 `/get`，即使自动模式关闭或没有浏览器打开也运行。
接收非 retained 的设备状态回报，以单调时钟判断新鲜度；90 秒没有状态回报、MQTT 断线或网关离线时，状态不再作为有效值展示。
`/device-status` 只读快照，不会为每次 HTTP 请求额外触发 Zigbee 查询。页面每 5 秒读一次快照，收到 WebSocket 设备事件时也立即读取；
WebSocket 的初始缓存不能绕过后台新鲜度判断。多浏览器共享同一查询流，不增加 Zigbee 轮询次数。
手动命令仍通过 WebSocket 发送，等待后台新的匹配状态版本后结束等待，不乐观改写图示。

部署路径：

- `/opt/plantctl-web/`：静态页面。
- `/etc/plantctl/web-nginx.conf`：专用 nginx 配置。
- `/etc/systemd/system/plantctl-web.service`：开机自启，异常退出重试。
- `/run/plantctl-web/`：运行时 PID 和临时文件。
- `/opt/plantctl-controller/controller/`：调度代码，不在网页根目录。
- `/var/lib/plantctl-scheduler/schedule.json`：持久化设置，由 systemd StateDirectory 管理（文件 0600）。
- `/etc/systemd/system/plantctl-scheduler.service`：独立开机自启，不依赖浏览器。
- 包自带 `nginx.service` 被 mask，防止默认站点意外开放；只运行专用 `plantctl-web.service`。

将 `web/`、`controller/` 和 `scripts/install-web.sh` 保持目录关系复制到设备，然后在设备运行：

```sh
sudo bash scripts/install-web.sh
systemctl status plantctl-web plantctl-scheduler
```

安装器面向现有 Debian Zigbee 主机；拒绝活动的系统 nginx 和无归属的目标目录。需要 80 端口未被其他服务占用。
更新后可重新运行安装器，已有时间设置会保留。安装器会重启调度服务，若已有启用的规则，会立即对齐当前时段。
停止此网页用 `sudo systemctl disable --now plantctl-web`，不会停止定时或 Zigbee2MQTT。
停止定时应在页面关闭自动模式，或执行 `sudo systemctl disable --now plantctl-scheduler`；两者都不会自动关闭当前负载。

## 验证

```sh
node --test tests/test_web.cjs tests/test_schedule_ui.cjs tests/test_dial.cjs
uv run --with 'paho-mqtt>=2,<3' --with 'PyYAML>=6,<7' python -m unittest discover -s tests -p 'test_*.py' -v
uvx ruff check controller tests/test_schedule.py tests/test_device_monitor.py
uvx --with 'paho-mqtt>=2,<3' pyright controller tests/test_schedule.py tests/test_device_monitor.py
node --check web/app.js
node --check web/schedule.js
bash -n scripts/install-web.sh
```

已验证：真实 Wi-Fi 地址 HTTP 200、全新浏览器免登录自动连接、后台自动收到插座新状态、390px 手机宽度无横向溢出、
非允许源地址 403、跨源 API 403、未知 Host 403，以及 service enabled/active 和代理凭证 root/0600。
自动化测试覆盖无凭证自动连接、后台新鲜度和状态版本、等待设备确认、超时、离线、重连不重发、上游认证异常后的重试。
圆环版 axe 检查没有确定违规，SVG 叠层中的刻度及中央文字对比度被标为需人工确认；已检查桌面和手机截图，文字可读。
实机未发送开关指令以避免改变实际负载；ON/OFF 请求和状态确认流程在模拟 WebSocket 测试中验证。
调度新增验证：真实浏览器保持自动关闭，保存测试时间，重启调度服务并重新加载验证持久化，再恢复默认时间；全程没有派发定时开关命令。
单元测试覆盖日间/跨午夜、精确边界、手动覆盖、停用、规则修改、重启对齐、校时等待、断网补当前状态、无效输入、落盘失败和并发版本冲突；通过真实 HTTP 接口验证保存和拒绝逻辑。
图示已验证真实设备 OFF 时无光束，ON/OFF/未知及断线状态传播在模拟网关与状态 API 测试中验证。
圆环已用真实浏览器鼠标拖拽和点按设置跨午夜时段，保存并重新加载确认；随后通过键盘调整恢复 08:00 → 22:00。全程保持自动关闭。
iPhone 12 浏览器模拟下用 CDP 真实触摸事件验证拖动、半小时吸附、圆环内不滚动页面及 touchCancel 回滚；未做真实手机辅助技术验证。
后台状态测试覆盖 retained 缓存不算新鲜、90 秒过期、断线恢复、无浏览器主动查询、多次 API 读取不增加设备查询；实机查询版本自动递增，未发送开关命令。
新网页和调度服务尚未经过整机重启或真实灯具跨定时边界验证，不能将此前网络重启测试视为这些服务的重启测试。
