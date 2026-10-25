# Plantctl 局域网控制页

## 访问

- 无线：<http://192.168.50.102/>
- 有线接通时：<http://192.168.50.101/>
- 原 Zigbee2MQTT 管理页保留在 `:8080`，配对和高级设置仍在那里操作。

无需 HTTPS 证书。手机或电脑须能访问 `192.168.50.0/24` 局域网；访客 Wi-Fi 的客户端隔离可能阻止访问。
输入原 Zigbee2MQTT 网页访问密码，不是 Wi-Fi 或 SSH 密码。密码仅保存在标签页内存，刷新需要重新输入。
HTTP 不加密，仅适用于可信局域网，禁止公网端口映射。页面所有素材本地提供，没有 CDN、外部字体或云服务依赖。

## 当前范围

- 为现有的 `plant-light` 提供状态、功率、电压、累计用电和 ON/OFF 操作。
- 状态标为“最近上报”，不是持续在线保证。可点击查询请求新的设备上报。
- 发出开关请求不立即改写显示状态；收到匹配状态报告才确认。超时、断线显示结果未确认，不自动重发控制指令。
- 断开网页不会关闭插座；网页没有后台调度逻辑。
- 不包含定时、节假日、历史图表、多设备管理或安全浇水逻辑。

## 架构与部署

`web/` 是无构建依赖的 HTML/CSS/JavaScript 页面。专用 nginx 实例在 IPv4 80 端口提供静态资源，
同源 `/api` WebSocket 代理到现有 `127.0.0.1:8080/api`。认证继续由 Zigbee2MQTT 负责，不复制密码或 Zigbee 密钥。
只有收到受保护数据才认为连接已鉴权，不能把 WebSocket 升级成功视为授权成功。

nginx 允许 `127.0.0.1` 和 `192.168.50.0/24`，其他来源返回 403；API 要求同源 Origin。
不开放 MQTT，不修改原网关或原防火墙。关闭访问日志和 API 错误日志以避免记录查询参数中的 Token。
静态资源使用 CSP、禁止嵌入、无缓存等响应头。服务使用 DynamicUser、只读系统及受限绑定端口能力。

部署路径：

- `/opt/plantctl-web/`：静态页面。
- `/etc/plantctl/web-nginx.conf`：专用 nginx 配置。
- `/etc/systemd/system/plantctl-web.service`：开机自启，异常退出重试。
- `/run/plantctl-web/`：运行时 PID 和临时文件。
- 包自带 `nginx.service` 被 mask，防止默认站点意外开放；只运行专用 `plantctl-web.service`。

将 `web/` 和 `scripts/install-web.sh` 保持目录关系复制到设备，然后在设备运行：

```sh
sudo bash scripts/install-web.sh
systemctl status plantctl-web
```

安装器面向现有 Debian Zigbee 主机；拒绝活动的系统 nginx 和无归属的目标目录。需要 80 端口未被其他服务占用。
更新页面后可重新运行安装器。停止此网页用 `sudo systemctl disable --now plantctl-web`；不会停止 Zigbee2MQTT 或改变插座状态。

## 验证

```sh
node --test tests/test_web.cjs
node --check web/app.js
bash -n scripts/install-web.sh
```

已验证：真实 Wi-Fi 地址 HTTP 200、浏览器使用原密码登录、只读查询收到插座新状态、390px 手机宽度无横向溢出、
未授权密码拒绝、非允许源地址 403、跨源 API 403，以及 service enabled/active。
自动化测试覆盖升级不等于认证、等待设备确认、超时、离线、重连不重发、退出清除状态。
实机未发送开关指令以避免改变实际负载；ON/OFF 请求和状态确认流程在模拟 WebSocket 测试中验证。
新网页服务尚未经过整机重启验证，不能将此前网络重启测试视为此服务的重启测试。
