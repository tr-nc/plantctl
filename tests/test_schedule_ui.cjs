const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const settle = () => new Promise((resolve) => setImmediate(resolve));
function page(enabled = false) {
  const nodes = new Map(),
    requests = [],
    events = [],
    timers = new Map();
  let poll,
    dial,
    timerId = 0,
    focused;
  class ScheduleDial {
    constructor(root, onChange, onCommit) {
      this.times = { on: "08:00", off: "22:00" };
      this.onChange = onChange;
      this.onCommit = onCommit;
      dial = this;
    }
    setRange(on, off) {
      this.times = { on, off };
    }
    setDisabled(value) {
      this.disabled = value;
    }
    edit(edge, value) {
      if (this.disabled) return;
      this.times[edge] = value;
      this.onChange();
    }
    finish(kind = "pointer") {
      this.onCommit(kind);
    }
  }
  const server = {
    enabled,
    on: "08:00",
    off: "22:00",
    revision: 0,
    clock_ready: true,
    gateway_online: true,
  };
  const get = (id) => {
    if (!nodes.has(id))
      nodes.set(id, {
        disabled: false,
        hidden: false,
        textContent: "",
        dataset: {},
        attrs: {},
        addEventListener(event, fn) {
          this[event] = fn;
        },
        setAttribute(k, v) {
          this.attrs[k] = v;
        },
        focus() {
          focused = id;
        },
      });
    return nodes.get(id);
  };
  const network = { fail: false };
  vm.runInNewContext(
    fs.readFileSync("web/schedule.js", "utf8").replace(/^import .*;\n/, ""),
    {
      ScheduleDial,
      document: { getElementById: get },
      AbortController,
      window: {
        dispatchEvent(event) {
          events.push(event.detail);
        },
      },
      CustomEvent: class {
        constructor(name, options) {
          this.detail = options.detail;
        }
      },
      setTimeout(fn, delay) {
        timers.set(++timerId, { fn, delay });
        return timerId;
      },
      clearTimeout(id) {
        timers.delete(id);
      },
      setInterval(fn) {
        poll = fn;
      },
      async fetch(url, options) {
        requests.push({ url, ...options });
        if (network.fail) throw new Error("offline");
        let status = 200,
          data = { ...server };
        if (options.method === "PUT") {
          const plan = JSON.parse(options.body);
          if (plan.revision !== server.revision) {
            status = 409;
            data = { error: "conflict" };
          } else {
            Object.assign(server, plan, { revision: server.revision + 1 });
            data = { ...server };
          }
        }
        return { ok: status === 200, status, json: async () => data };
      },
    },
  );
  return {
    get,
    dial,
    server,
    requests,
    events,
    network,
    timers,
    poll: () => poll(),
    focused: () => focused,
  };
}
test("tabs own persisted mode, panels are exclusive, unknown and saving states lock controls", async () => {
  const p = page();
  assert.equal(p.get("tab-auto").disabled, true);
  await settle();
  assert.equal(p.get("manual-panel").hidden, false);
  assert.equal(p.get("schedule-editor").hidden, true);
  assert.equal(p.dial.disabled, true);
  const saving = p.get("tab-auto").onclick();
  assert.equal(p.get("tab-manual").disabled, true);
  assert.equal(p.events.at(-1).locked, true);
  await saving;
  assert.equal(p.server.enabled, true);
  assert.equal(p.get("manual-panel").hidden, true);
  assert.equal(p.get("schedule-editor").hidden, false);
  assert.equal(p.dial.disabled, false);
  assert.equal(p.get("schedule-feedback").hidden, true);
  await p.get("tab-manual").onclick();
  assert.equal(p.server.enabled, false);
  assert.equal(p.dial.disabled, true);
});
test("drag previews do not write; release saves once without a save button", async () => {
  const p = page(true);
  await settle();
  p.dial.edit("on", "09:00");
  p.dial.edit("on", "09:30");
  await p.poll();
  assert.equal(p.requests.filter((r) => r.method === "PUT").length, 0);
  assert.equal(p.dial.times.on, "09:30");
  p.dial.finish();
  await settle();
  assert.equal(p.server.on, "09:30");
  assert.equal(p.requests.filter((r) => r.method === "PUT").length, 1);
  assert.doesNotMatch(
    fs.readFileSync("web/index.html", "utf8"),
    /schedule-save|schedule-enabled|schedule-hint/,
  );
});
test("keyboard changes coalesce and switching mode discards unsaved preview", async () => {
  const p = page(true);
  await settle();
  p.dial.edit("on", "09:00");
  p.dial.finish("keyboard");
  p.dial.edit("on", "09:30");
  p.dial.finish("keyboard");
  const delayed = [...p.timers.values()].filter((t) => t.delay === 400);
  assert.equal(delayed.length, 1);
  delayed[0].fn();
  await settle();
  assert.equal(p.server.on, "09:30");
  p.dial.edit("on", "10:00");
  await p.get("tab-manual").onclick();
  assert.equal(p.server.on, "09:30");
  assert.equal(p.dial.times.on, "09:30");
  const before = p.requests.length;
  p.get("tab-manual").keydown({ key: "ArrowRight", preventDefault() {} });
  assert.equal(p.focused(), "tab-auto");
  assert.equal(p.requests.length, before);
});
test("a pending keyboard save cannot commit an in-progress pointer preview", async () => {
  const p = page(true);
  await settle();
  p.dial.edit("on", "09:00");
  p.dial.finish("keyboard");
  p.dial.drag = {};
  p.dial.edit("on", "10:00");
  [...p.timers.values()].find((t) => t.delay === 400).fn();
  await settle();
  assert.equal(p.requests.filter((r) => r.method === "PUT").length, 0);
  p.dial.drag = null;
  p.dial.finish();
  await settle();
  assert.equal(p.server.on, "10:00");
  assert.equal(p.requests.filter((r) => r.method === "PUT").length, 1);
});
test("conflicts reload authoritative times and remote manual mode locks the dial", async () => {
  const p = page(true);
  await settle();
  p.dial.edit("on", "10:00");
  p.server.on = "19:00";
  p.server.revision = 1;
  p.dial.finish();
  await settle();
  assert.equal(p.dial.times.on, "19:00");
  assert.match(p.get("schedule-feedback").textContent, /其他设备/);
  p.dial.edit("on", "20:00");
  p.server.enabled = false;
  p.server.revision++;
  await p.poll();
  assert.equal(p.dial.disabled, true);
  assert.equal(p.dial.times.on, "19:00");
  assert.equal(p.get("manual-panel").hidden, false);
});
test("failed mode switches never claim success and reconnect restores server state", async () => {
  const p = page();
  await settle();
  p.network.fail = true;
  await p.get("tab-auto").onclick();
  assert.equal(p.get("manual-panel").hidden, false);
  assert.equal(p.get("schedule-editor").hidden, true);
  assert.equal(p.get("tab-auto").disabled, true);
  assert.match(p.get("schedule-feedback").textContent, /无法确认/);
  p.network.fail = false;
  await p.poll();
  assert.equal(p.get("tab-auto").disabled, false);
  assert.equal(p.get("schedule-feedback").hidden, true);
});
