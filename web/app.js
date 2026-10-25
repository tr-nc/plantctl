const $ = (id) => document.getElementById(id);
let socket, retry, deadline;
let authenticated = false;
let pending = null;
let health = null;
let reading = false;
let operationMessage = "";
let connectionError = "";
let statusError = "";

function render() {
  const connected = authenticated && socket?.readyState === WebSocket.OPEN;
  const ready = connected && health?.gateway_online;
  const fresh = ready && health?.fresh;
  const report = fresh ? health.report : {};
  $("device-visual").dataset.state =
    report.state === "ON" ? "on" : report.state === "OFF" ? "off" : "unknown";
  $("connection").textContent = !connected
    ? "连接中"
    : !health
      ? "状态不可用"
      : !health.gateway_online
        ? "网关离线"
        : !fresh
          ? "设备未响应"
          : "● 已连接";
  $("connection").classList.toggle("online", !!fresh);
  for (const id of ["on", "off"]) $(id).disabled = !ready || !!pending;
  $("state-badge").textContent =
    report.state === "ON"
      ? "已开启"
      : report.state === "OFF"
        ? "已关闭"
        : "状态待确认";
  $("state-badge").classList.toggle("online", report.state === "ON");
  $("power").textContent =
    typeof report.power === "number" ? report.power : "—";
  $("voltage").textContent =
    `${typeof report.voltage === "number" ? report.voltage : "—"} V`;
  $("energy").textContent =
    `${typeof report.energy === "number" ? report.energy : "—"} kWh`;
  const message =
    operationMessage ||
    connectionError ||
    statusError ||
    (connected && health?.gateway_online && !fresh
      ? "设备暂未响应，后台正在自动查询。"
      : "");
  $("feedback").textContent = message;
  $("feedback").hidden = !message;
}
function clearPending() {
  clearTimeout(deadline);
  pending = null;
}
async function loadHealth() {
  if (reading) return;
  reading = true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch("/device-status", {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!response.ok) throw new Error("Unavailable");
    const value = await response.json();
    if (
      !value ||
      typeof value.fresh !== "boolean" ||
      typeof value.version !== "string"
    )
      throw new Error("Invalid state");
    const changed = value.version !== health?.version;
    health = value;
    statusError = "";
    if (
      pending &&
      value.fresh &&
      value.version !== pending.version &&
      value.report.state === pending.state
    ) {
      clearPending();
      operationMessage = "";
    } else if (!pending && changed && value.fresh) operationMessage = "";
  } catch {
    health = null;
    statusError = "状态服务暂不可用，正在自动重试。";
  } finally {
    clearTimeout(timeout);
    reading = false;
    render();
  }
}
function connect() {
  clearTimeout(retry);
  authenticated = false;
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
    authenticated = true;
    connectionError = "";
    clearTimeout(authTimeout);
    // WebSocket events prompt a read of the server-owned, freshness-checked state.
    // Never treat the gateway's cached initial payload as a fresh device report.
    if (["plant-light", "bridge/state"].includes(message.topic)) loadHealth();
    render();
  };
  ws.onclose = (event) => {
    clearTimeout(authTimeout);
    if (socket !== ws) return;
    authenticated = false;
    if (pending) operationMessage = "连接中断，操作结果待确认。";
    clearPending();
    connectionError =
      event.code === 4401 ? "网关配置异常，正在重试。" : "连接中断，正在重连。";
    render();
    retry = setTimeout(connect, 4000);
  };
  ws.onerror = () => {};
}
function send(state) {
  if (
    !authenticated ||
    !health?.gateway_online ||
    socket?.readyState !== WebSocket.OPEN ||
    pending
  )
    return;
  pending = { state, version: health.version };
  socket.send(JSON.stringify({ topic: "plant-light/set", payload: { state } }));
  operationMessage = "等待设备确认…";
  deadline = setTimeout(() => {
    clearPending();
    operationMessage = "暂未收到操作确认，后台会继续查询。";
    render();
  }, 15000);
  render();
}
$("on").onclick = () => send("ON");
$("off").onclick = () => send("OFF");
connect();
loadHealth();
setInterval(loadHealth, 5000);
