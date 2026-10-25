import { ScheduleDial } from "./dial.mjs";

const el = (id) => document.getElementById(id);
const dial = new ScheduleDial(el("schedule-dial"), () => {
  controls();
  note(dirty() ? "尚未保存" : "每天 · 北京时间");
});
let saved = null;
let busy = false;
let available = false;
let reading = false;
let writes = 0;

function dirty() {
  return saved && (dial.times.on !== saved.on || dial.times.off !== saved.off);
}
function controls() {
  el("schedule-enabled").disabled = busy || !available;
  const disabled = busy || !available || !saved?.enabled;
  dial.setDisabled(disabled);
  el("schedule-editor").dataset.disabled = String(disabled);
  el("schedule-mode").textContent = busy
    ? "保存中"
    : !available
      ? "未连接"
      : saved?.enabled
        ? "已开启"
        : "已关闭";
  el("schedule-save").disabled = disabled || !dirty();
}
function note(text) {
  el("schedule-feedback").textContent = text;
}
function show(data, force = false) {
  if (dial.drag && !force && data.enabled) return;
  const preserveDraft = dirty() && !force && data.enabled;
  if (!preserveDraft) {
    saved = data;
    el("schedule-enabled").checked = data.enabled;
    dial.setRange(data.on, data.off);
  }
  if (!data.enabled) note("开启自动开关后可调整时间。");
  else if (!data.clock_ready) note("等待系统校时，暂不执行。");
  else if (!data.gateway_online) note("网关离线，恢复后按当前时段执行。");
  else if (data.next) {
    const time = new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(data.next.at));
    note(`${time} ${data.next.state === "ON" ? "开灯" : "关灯"} · 北京时间`);
  }
  if (preserveDraft) note("时间已修改，尚未保存。");
  controls();
}
async function request(method = "GET", body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch("/schedule", {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
      cache: "no-store",
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error || "定时服务不可用。");
      error.conflict = response.status === 409;
      throw error;
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}
async function load() {
  if (busy || reading) return;
  reading = true;
  const generation = writes;
  try {
    const data = await request();
    if (busy || generation !== writes) return;
    available = true;
    show(data);
  } catch {
    if (!busy && generation === writes) {
      available = false;
      note("定时服务无法连接，已有规则可能仍在执行。");
      controls();
    }
  } finally {
    reading = false;
  }
}
async function save() {
  if (busy || !available || !saved) return;
  if (dial.times.on === dial.times.off) {
    el("schedule-enabled").checked = saved.enabled;
    note("开启和关闭时间不能相同。");
    return;
  }
  busy = true;
  writes += 1;
  controls();
  note("正在保存…");
  try {
    const data = await request("PUT", {
      enabled: el("schedule-enabled").checked,
      ...dial.times,
      revision: saved.revision,
    });
    show(data, true);
  } catch (error) {
    el("schedule-enabled").checked = saved.enabled;
    if (error.conflict) {
      try {
        show(await request(), true);
        note("已加载其他设备的更新，请重新编辑。");
      } catch {
        note("配置有冲突，请刷新页面后重试。");
      }
    } else {
      note("保存未确认，请刷新核对；现有规则可能仍在执行。");
    }
  } finally {
    busy = false;
    controls();
  }
}
el("schedule-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (saved?.enabled) save();
});
el("schedule-enabled").addEventListener("change", save);
controls();
load();
setInterval(load, 15000);
