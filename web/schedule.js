import { ScheduleDial } from "./dial.mjs";

const el = (id) => document.getElementById(id);
let saved = null;
let busy = false;
let available = false;
let reading = false;
let writes = 0;
let debounce;
const dial = new ScheduleDial(
  el("schedule-dial"),
  () => {},
  (kind) => {
    clearTimeout(debounce);
    if (kind === "keyboard") debounce = setTimeout(() => saveTimes(), 400);
    else saveTimes();
  },
);
function dirty() {
  return saved && (dial.times.on !== saved.on || dial.times.off !== saved.off);
}
function note(text = "") {
  el("schedule-feedback").textContent = text;
  el("schedule-feedback").hidden = !text;
}
function controls() {
  const locked = busy || !available || !saved;
  for (const [id, automatic] of [
    ["tab-manual", false],
    ["tab-auto", true],
  ]) {
    const tab = el(id);
    const selected = saved?.enabled === automatic;
    tab.disabled = !!locked;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  }
  el("manual-panel").hidden = !saved || saved.enabled;
  el("schedule-editor").hidden = !saved || !saved.enabled;
  const disabled = !!locked || !saved?.enabled;
  dial.setDisabled(disabled);
  el("schedule-editor").dataset.disabled = String(disabled);
  window.dispatchEvent(
    new CustomEvent("plantctl:schedule", {
      detail: {
        enabled: saved?.enabled ?? null,
        revision: saved?.revision ?? -1,
        locked: !!locked,
      },
    }),
  );
}
function show(data, force = false) {
  if (dial.drag && !force && data.enabled) return;
  if (!dirty() || force || !data.enabled) {
    saved = data;
    dial.setRange(data.on, data.off);
  }
  note();
  if (data.enabled && !data.clock_ready)
    note("系统正在校时，自动控制暂未执行。");
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
      const error = new Error(data.error || "设置服务不可用。");
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
      note("控制服务无法连接，已有规则可能仍在执行。");
      controls();
    }
  } finally {
    reading = false;
  }
}
async function save(enabled, times) {
  if (busy || !available || !saved) return;
  clearTimeout(debounce);
  busy = true;
  writes += 1;
  controls();
  note();
  try {
    const data = await request("PUT", {
      enabled,
      ...times,
      revision: saved.revision,
    });
    show(data, true);
  } catch (error) {
    try {
      show(await request(), true);
      note(
        error.conflict
          ? "设置已在其他设备更新，请重新调整。"
          : "修改未确认，已重新读取当前设置。",
      );
    } catch {
      available = false;
      note("无法确认设置，正在重连；已有规则可能仍在执行。");
    }
  } finally {
    busy = false;
    controls();
  }
}
async function saveTimes() {
  if (!saved?.enabled || !dirty()) return;
  if (dial.drag) {
    debounce = setTimeout(() => saveTimes(), 400);
    return;
  }
  await save(true, dial.times);
}
function switchMode(enabled) {
  if (!saved || saved.enabled === enabled) return;
  return save(enabled, { on: saved.on, off: saved.off });
}
for (const [id, enabled] of [
  ["tab-manual", false],
  ["tab-auto", true],
]) {
  el(id).onclick = () => switchMode(enabled);
  el(id).addEventListener("keydown", (event) => {
    // Arrow keys move focus only; Enter/Space explicitly activate the mode.
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const target =
        event.key === "Home"
          ? "tab-manual"
          : event.key === "End"
            ? "tab-auto"
            : enabled
              ? "tab-manual"
              : "tab-auto";
      el(target).focus();
    }
  });
}
el("schedule-form").addEventListener("submit", (event) =>
  event.preventDefault(),
);
controls();
load();
setInterval(load, 15000);
