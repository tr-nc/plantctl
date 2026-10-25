const $ = (id) => document.getElementById(id);
let socket,
  token = "",
  retry,
  deadline,
  pending = null,
  authenticated = false,
  bridgeOnline = false;
let report = {};
const device = "plant-light";
$("date").textContent = new Intl.DateTimeFormat("zh-CN", {
  month: "long",
  day: "numeric",
  weekday: "long",
}).format(new Date());
function feedback(text) {
  $("feedback").textContent = text;
}
function render() {
  const connected = authenticated && socket?.readyState === WebSocket.OPEN;
  const ready = connected && bridgeOnline;
  $("connection").textContent = ready
    ? "● 网关已连接"
    : connected
      ? "网关离线"
      : "未连接";
  $("connection").classList.toggle("online", ready);
  for (const id of ["on", "off", "refresh"])
    $(id).disabled = !ready || !!pending;
  $("state-badge").textContent = !ready
    ? "状态待确认"
    : report.state === "ON"
      ? "最近上报 · 已开启"
      : report.state === "OFF"
        ? "最近上报 · 已关闭"
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
    `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api?token=${encodeURIComponent(token)}`,
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
    // A successful upgrade alone is NOT authentication: only protected data proves it.
    if (!authenticated) {
      authenticated = true;
      clearTimeout(authTimeout);
      $("login").hidden = true;
      $("logout").hidden = false;
      $("password").value = "";
      feedback("已连接。显示最近上报值；可点击查询获取新状态。");
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
        feedback(
          `收到设备状态：${payload.state === "ON" ? "已开启" : "已关闭"} · ${new Date().toLocaleTimeString("zh-CN")}`,
        );
      }
    }
    if (!bridgeOnline && pending) {
      clearPending();
      feedback("网关已离线，操作结果未确认，请恢复连接后查询。");
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
    if (event.code === 4401) {
      token = "";
      $("login").hidden = false;
      $("logout").hidden = true;
      feedback("网页访问密码不正确，请重新输入。");
    } else if (token) {
      feedback("连接已中断，操作结果未确认；正在重连，不会自动重发开关指令。");
      retry = setTimeout(connect, 4000);
    }
  };
  ws.onerror = () => {
    /* close handles retry; never display a URL containing the token */
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
  feedback(
    state === "QUERY"
      ? "正在查询，等待设备上报…"
      : "指令已发送，等待设备上报；尚未确认执行。",
  );
  deadline = setTimeout(() => {
    clearPending();
    feedback(
      "暂未收到匹配的设备上报。请检查插座供电并查询状态；不会自动重发指令。",
    );
    render();
  }, 12000);
  render();
}
$("login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  clearTimeout(retry);
  clearPending();
  const old = socket;
  socket = null;
  old?.close();
  token = $("password").value;
  feedback("正在连接网关…");
  connect();
});
$("on").onclick = () => send("ON");
$("off").onclick = () => send("OFF");
$("refresh").onclick = () => send("QUERY");
$("logout").onclick = () => {
  clearTimeout(retry);
  clearPending();
  token = "";
  authenticated = false;
  bridgeOnline = false;
  const old = socket;
  socket = null;
  old?.close();
  report = {};
  $("login").hidden = false;
  $("logout").hidden = true;
  feedback("已断开连接，设备的开关状态不会因此改变。");
  render();
};
render();
