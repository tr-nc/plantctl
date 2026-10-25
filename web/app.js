const $ = (id) => document.getElementById(id);
let socket,
  retry,
  deadline,
  pending = null,
  authenticated = false,
  bridgeOnline = false;
let report = {};
const device = "plant-light";
function feedback(text) {
  $("feedback").textContent = text;
}
function render() {
  const connected = authenticated && socket?.readyState === WebSocket.OPEN;
  const ready = connected && bridgeOnline;
  $("device-visual").dataset.state =
    ready && report.state === "ON"
      ? "on"
      : ready && report.state === "OFF"
        ? "off"
        : "unknown";
  $("connection").textContent = ready
    ? "● 已连接"
    : connected
      ? "网关离线"
      : "未连接";
  $("connection").classList.toggle("online", ready);
  for (const id of ["on", "off", "refresh"])
    $(id).disabled = !ready || !!pending;
  $("state-badge").textContent = !ready
    ? "状态待确认"
    : report.state === "ON"
      ? "已开启"
      : report.state === "OFF"
        ? "已关闭"
        : "状态未知";
  $("state-badge").classList.toggle("online", ready && report.state === "ON");
  $("power").textContent =
    typeof report.power === "number" ? report.power : "—";
  $("voltage").textContent =
    `${typeof report.voltage === "number" ? report.voltage : "—"} V`;
  $("energy").textContent =
    `${typeof report.energy === "number" ? report.energy : "—"} kWh`;
}
function clearPending() {
  clearTimeout(deadline);
  pending = null;
}
function connect() {
  clearTimeout(retry);
  authenticated = false;
  bridgeOnline = false;
  report = {};
  render();
  const ws = new WebSocket(
    `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api`,
  );
  socket = ws;
  const authTimeout = setTimeout(() => {
    if (!authenticated && socket === ws) ws.close();
  }, 10000);
  ws.onmessage = ({ data }) => {
    if (socket !== ws) return;
    let message;
    try {
      message = JSON.parse(data);
    } catch {
      return;
    }
    if (!message || typeof message.topic !== "string") return;
    // The proxy authenticates upstream; wait for gateway data, not just an upgrade.
    if (!authenticated) {
      authenticated = true;
      clearTimeout(authTimeout);
      feedback("最近上报");
    }
    const { topic, payload } = message;
    if (topic === "bridge/state") bridgeOnline = payload?.state === "online";
    if (topic === device && payload && typeof payload === "object") {
      report = { ...report, ...payload };
      if (
        pending &&
        (pending === "QUERY"
          ? ["ON", "OFF"].includes(payload.state)
          : pending === payload.state)
      ) {
        clearPending();
        feedback(`已更新 · ${new Date().toLocaleTimeString("zh-CN")}`);
      }
    }
    if (!bridgeOnline && pending) {
      clearPending();
      feedback("网关离线，操作结果待确认。");
    }
    render();
  };
  ws.onclose = (event) => {
    clearTimeout(authTimeout);
    if (socket !== ws) return;
    authenticated = false;
    bridgeOnline = false;
    clearPending();
    render();
    feedback(
      event.code === 4401
        ? "网关配置异常，正在重试。"
        : "连接中断，正在重连。操作结果待确认。",
    );
    retry = setTimeout(connect, 4000);
  };
  ws.onerror = () => {
    /* close handles retry */
  };
}
function send(state) {
  if (
    !authenticated ||
    !bridgeOnline ||
    socket?.readyState !== WebSocket.OPEN ||
    pending
  )
    return;
  pending = state;
  socket.send(
    JSON.stringify({
      topic: `${device}/${state === "QUERY" ? "get" : "set"}`,
      payload: { state: state === "QUERY" ? "" : state },
    }),
  );
  feedback(state === "QUERY" ? "正在查询…" : "已发送，等待设备确认…");
  deadline = setTimeout(() => {
    clearPending();
    feedback("暂未收到确认，请检查插座供电后刷新。");
    render();
  }, 12000);
  render();
}
$("on").onclick = () => send("ON");
$("off").onclick = () => send("OFF");
$("refresh").onclick = () => send("QUERY");
feedback("正在连接…");
connect();
