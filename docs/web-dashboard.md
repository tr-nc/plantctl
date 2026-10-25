# Plantctl 局域网控制页

## 访问与界面

- 无线：<http://192.168.50.102/>；有线接通时：<http://192.168.50.101/>。
- 手机和电脑可直接访问，无需证书或网页密码。HTTP 不加密，仅适用于可信局域网，禁止公网端口映射。
- 原 Zigbee2MQTT 高级管理页保留在 `:8080`，仍使用原网页密码；配对和高级设置在那里操作。
- 左侧仅显示 `plant-light` 的图示、开关状态、功率、电压和累计用电。
- 右侧为统一控制区，只有 **手动 / 自动** 两个模式 Tab；没有额外自动开关、保存按钮、正常状态下的更新时间或说明小字。
- 页面素材均在本地，不依赖 CDN 或云服务。访客 Wi-Fi 的客户端隔离可能阻止访问。

## 模式契约

Tab 选择的是**实际运行模式**，不是只切换可见内容：

- **手动**：持久化 `enabled=false`，停止自动派发，显示开灯/关灯按钮，隐藏并锁定时间盘。切到手动不自动关灯。
- **自动**：持久化 `enabled=true`，按当前时段对齐一次，显示时间盘，隐藏并禁用手动按钮。
- 保存成功后才切换选中 Tab；等待中禁止重复操作，失败时核对服务端配置或显示未确认提示。
- Tab 方向键仅移动焦点，Enter/Space 才激活，避免单纯键盘浏览就切换实际模式。
- 其他浏览器改模式后，本页同步；客户端配置版本防止旧状态覆盖新状态。
- 日常手动命令统一通过 `POST /manual`，服务端在调度器的同一锁内检查模式、网关可用性并派发。自动模式返回 409，不发送 MQTT；不能只靠按钮禁用。
- 这不是设备安全联锁：插座物理按钮、原 Zigbee 高级界面/原始 WebSocket API 不经过该日常控制接口。可信 LAN 代理仍具有原网关完整 API 能力，不是分角色权限隔离。升级后的旧页面须刷新以使用新接口。

## 圆环与自动保存

- 默认手动模式；初始时间为 `08:00 → 22:00`。已有设置不因部署而覆盖。
- 固定使用 **Asia/Shanghai（北京时间）**，不依赖手机时区或主机 UTC 显示。每天重复，支持跨午夜。
- 24 小时圆环：顶部 00、右侧 06、底部 12、左侧 18。亮色弧表示亮灯时段，中央显示时长。
- 端点按半小时吸附；也可选中下方开启/关闭时间卡片，再点按圆环定位，不需要打字。
- 拖动过程只预览，**松手立即保存**。一次手势只提交一次，避免经过中间时刻就反复控制实际负载；取消手势回滚，不提交。
- 键盘方向键调整半小时，Home/End 定位 00:00/23:30；连续按键停止 400ms 后合并保存。拖拽进行中不会被待执行的键盘保存打断。
- 开关时间不能重合。旧 HH:MM 设置不静默取整，调整对应端点时才吸附。
- 没有保存成功小字，正常情况无反馈横幅；保存失败、冲突、校时未完成等异常仍显示必要提示。
- 修改时段或切换到自动后立即对齐当前时段；切换模式使用已保存的时间，放弃尚未提交的预览。
- 配置原子写入并 fsync 后才激活；写失败不能显示成成功。
- 交互依据与可访问性边界见 [圆环调研](schedule-dial-research.md)。

## 后台执行与状态

调度运行在 Orange Pi 的独立 `plantctl-scheduler.service`，不是浏览器定时器。关闭网页、管理电脑离线、停止网页服务都不会停止已启用的规则。

- 每秒检查边界；开启时间包含在亮灯时段内，关闭时间起熄灯，不承诺硬实时。
- 启用、改规则或调度服务重启后对齐当前时段。断网恢复后只补当前状态，不重放多个错过的动作。
- 等待本次启动的 systemd-timesyncd 校时标记后才执行，避免错误时钟触发动作。持续供电且已校时后，网络中断不停止本地计时或 Zigbee 控制。
- MQTT 指令不保留、不持久排队。提交成功不等于物理执行；不自动重发已提交开关指令，不是安全浇水保护器。
- 后台统一每 30 秒发送一次只读 `/get`，网关恢复立即查询；自动模式关闭、没有浏览器打开也运行。
- 非 retained 的设备状态回报才算新鲜，使用单调时钟判断；90 秒无状态、MQTT 断线或网关离线时，不展示过期值为有效状态。
- 浏览器每 5 秒读取 `/device-status`，收到 WebSocket 设备事件时也立即读取。API 快照读取不会增加 Zigbee 查询，多浏览器共享同一查询流。
- 左侧图示由后台新鲜状态驱动：ON 有光束，OFF 灭灯变暗，未知/断线为中性灰色。手动请求等待新的匹配状态版本，不乐观改图示。

## API 与部署

无构建依赖的静态 `web/` 由专用 nginx 实例在 IPv4 80 端口提供。Python `controller/` 使用 Paho MQTT 2.x 连接本地 Broker。
API 仅监听 `127.0.0.1:8091`，经 nginx 代理：

| 接口 | 用途 |
| --- | --- |
| `GET /schedule` | 读取模式、时段、配置版本和运行信息 |
| `PUT /schedule` | 保存 `{enabled, on, off, revision}`，版本冲突 409 |
| `GET /device-status` | 只读状态、新鲜度、状态版本、自动模式及配置版本 |
| `POST /manual` | `{state: "ON" / "OFF"}`，自动模式拒绝 409；离线返回 503 |

写请求必须同源并使用 JSON。nginx 仅允许 `127.0.0.1` 和 `192.168.50.0/24`；Host 白名单限 `.101`、`.102`、回环、localhost、orangepizero3.lan/local。
只读事件 WebSocket 仍连接同源 `/api`，代理到原网关 `127.0.0.1:8080/api`；新日常页面不再通过它发送开关命令。
代理 Token 由安装器从原配置生成 root/0600 的 `/etc/plantctl/web-upstream.conf`，通过 systemd LoadCredential 提供给 nginx，不交给浏览器。
原始代理未做消息级写过滤，不能把“页面只读使用”理解为网络 API 的只读权限。更换原网关密码后需重新运行安装器。
访问日志和代理错误日志避免记录 Token，静态响应有 CSP/禁止嵌入/无缓存保护。服务以 DynamicUser 运行，不开放 MQTT 到 LAN。

关键路径：

- `/opt/plantctl-web/`：页面；`/etc/plantctl/web-nginx.conf`：专用 nginx 配置。
- `/etc/systemd/system/plantctl-web.service`：开机自启；包自带 `nginx.service` 被 mask。
- `/opt/plantctl-controller/controller/`：后台代码，不在网页根目录。
- `/var/lib/plantctl-scheduler/schedule.json`：0600 持久化设置，systemd StateDirectory 管理。
- `/etc/systemd/system/plantctl-scheduler.service`：后台服务，异常退出重启。调度主线程异常不能留下假正常 API。

将 `web/`、`controller/` 和 `scripts/install-web.sh` 保持目录关系复制到现有 Debian Zigbee 主机，然后运行：

```sh
sudo bash scripts/install-web.sh
systemctl status plantctl-web plantctl-scheduler
```

安装器会重启调度服务；已启用时会按原规则对齐当前状态，部署前应检查实际设置。
停止网页不停止调度；停用调度请切到手动模式。`sudo systemctl disable --now plantctl-scheduler` 会停止调度及日常控制 API，但不会自动关闭负载。

## 验证与边界

```sh
node --test tests/test_web.cjs tests/test_schedule_ui.cjs tests/test_dial.cjs
uv run --with 'paho-mqtt>=2,<3' --with 'PyYAML>=6,<7' python -m unittest discover -s tests -p 'test_*.py' -v
uvx ruff check controller tests/test_schedule.py tests/test_device_monitor.py
uvx --with 'paho-mqtt>=2,<3' pyright controller tests/test_schedule.py tests/test_device_monitor.py
bash -n scripts/install-web.sh
```

- 测试覆盖：模式互斥（包括服务端 409）、离线拒绝、过期页面、乱序配置响应、保存失败/冲突恢复、跨午夜、校时、持久化、状态过期、一次拖动只在结束时提交、取消与键盘合并保存。
- 实际部署页面使用模拟 API 验证 Tab 切换、手动/自动面板互斥、左侧无控制按钮、拖动中零次提交/松手一次提交，以及无保存按钮/说明小字。没有借交互测试修改用户真实模式或时段。
- 首版已验证实际配置保存及调度服务重启后保留。当前用户自行设置的 `15:00 → 16:30` 保持不变；更新后观察到既有规则在 15:00 派发 ON，设备随后报告 ON、功率约 23W。这是既有规则自然执行的观察，不是测试额外发送的手动命令。
- 桌面和 390px 手机布局已检查；axe 无确定违规，SVG 叠层部分文字需人工确认，已检查截图。早期圆环已用模拟触摸验证捕获、吸附和取消；未做真实手机辅助技术验证。
- 新网页和调度服务未经过整机重启或突然断电测试，不能把此前网络重启测试视为这些服务的重启测试。不包含节假日或安全浇水逻辑。
