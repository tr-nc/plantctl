const el = (id) => document.getElementById(id);
let saved = null;
let busy = false;
let available = false;
let reading = false;
let writes = 0;

function dirty() {
  return (
    saved &&
    (el("schedule-on").value !== saved.on ||
      el("schedule-off").value !== saved.off)
  );
}
function controls() {
  for (const id of ["schedule-enabled", "schedule-on", "schedule-off"])
    el(id).disabled = busy || !available;
  el("schedule-save").disabled = busy || !available || !dirty();
}
function note(text) {
  el("schedule-feedback").textContent = text;
}
function show(data, force = false) {
  const preserveDraft = dirty() && !force;
  if (!preserveDraft) {
    saved = data;
    el("schedule-enabled").checked = data.enabled;
    el("schedule-on").value = data.on;
    el("schedule-off").value = data.off;
  }
  if (!data.enabled) note("每天 · 北京时间");
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
  if (!el("schedule-form").reportValidity()) {
    el("schedule-enabled").checked = saved.enabled;
    return;
  }
  if (el("schedule-on").value === el("schedule-off").value) {
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
      on: el("schedule-on").value,
      off: el("schedule-off").value,
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
  save();
});
el("schedule-enabled").addEventListener("change", save);
for (const id of ["schedule-on", "schedule-off"])
  el(id).addEventListener("input", () => {
    controls();
    if (dirty()) note("时间已修改，尚未保存。");
  });
controls();
load();
setInterval(load, 15000);
