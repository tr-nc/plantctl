const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const settle = () => new Promise((resolve) => setImmediate(resolve));
function page(enabled = false) {
  const nodes = new Map(),
    requests = [];
  let poll, dial;
  class ScheduleDial {
    constructor(root, onChange) {
      this.times = { on: "08:00", off: "22:00" };
      this.onChange = onChange;
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
  }
  const server = {
    enabled,
    on: "08:00",
    off: "22:00",
    revision: 0,
    timezone: "Asia/Shanghai",
    clock_ready: true,
    gateway_online: true,
    next: null,
  };
  const get = (id) => {
    if (!nodes.has(id))
      nodes.set(id, {
        value: "",
        checked: false,
        disabled: false,
        textContent: "",
        dataset: {},
        addEventListener(event, fn) {
          this[event] = fn;
        },
        reportValidity() {
          return true;
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
      Date,
      Intl,
      AbortController,
      setTimeout() {
        return 1;
      },
      clearTimeout() {},
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
  return { get, dial, server, requests, network, poll: () => poll() };
}
test("loads persisted settings without writing; toggle saves immediately", async () => {
  const p = page();
  await settle();
  assert.equal(p.dial.times.on, "08:00");
  assert.equal(p.get("schedule-enabled").checked, false);
  assert.equal(p.requests.length, 1);
  assert.equal(p.dial.disabled, true);
  assert.equal(p.get("schedule-editor").dataset.disabled, "true");
  p.dial.edit("on", "09:00");
  assert.equal(p.dial.times.on, "08:00");
  p.get("schedule-enabled").checked = true;
  await p.get("schedule-enabled").change();
  assert.equal(p.server.enabled, true);
  assert.equal(p.dial.disabled, false);
  assert.equal(p.get("schedule-mode").textContent, "已开启");
  assert.equal(p.server.revision, 1);
  assert.deepEqual(JSON.parse(p.requests[1].body), {
    enabled: true,
    on: "08:00",
    off: "22:00",
    revision: 0,
  });
});
test("equal times are rejected, drafts survive polling, conflicts reload explicitly", async () => {
  const p = page(true);
  await settle();
  p.dial.edit("on", "22:00");
  p.get("schedule-enabled").checked = true;
  await p.get("schedule-enabled").change();
  assert.equal(p.server.enabled, true);
  assert.match(p.get("schedule-feedback").textContent, /不能相同/);
  p.dial.edit("on", "20:00");
  p.server.on = "19:00";
  p.server.revision = 1;
  await p.poll();
  assert.equal(p.dial.times.on, "20:00");
  p.get("schedule-enabled").checked = true;
  await p.get("schedule-enabled").change();
  assert.equal(p.dial.times.on, "19:00");
  assert.equal(p.server.enabled, true);
  assert.match(p.get("schedule-feedback").textContent, /其他设备/);
});
test("turning off locks editing and saving; remote disable discards stale drafts", async () => {
  const p = page(true);
  await settle();
  p.get("schedule-enabled").checked = false;
  await p.get("schedule-enabled").change();
  assert.equal(p.dial.disabled, true);
  assert.equal(p.get("schedule-save").disabled, true);
  assert.equal(p.get("schedule-enabled").disabled, false);
  assert.equal(p.get("schedule-mode").textContent, "已关闭");
  p.get("schedule-enabled").checked = true;
  await p.get("schedule-enabled").change();
  p.dial.edit("on", "09:00");
  p.server.enabled = false;
  p.server.revision++;
  await p.poll();
  assert.equal(p.dial.disabled, true);
  assert.equal(p.get("schedule-enabled").checked, false);
  assert.equal(p.dial.times.on, "08:00");
});
test("failed saves are not shown as enabled; connectivity loss disables editing", async () => {
  const p = page();
  await settle();
  p.network.fail = true;
  p.get("schedule-enabled").checked = true;
  await p.get("schedule-enabled").change();
  assert.equal(p.get("schedule-enabled").checked, false);
  assert.match(p.get("schedule-feedback").textContent, /未确认/);
  await p.poll();
  assert.equal(p.get("schedule-enabled").disabled, true);
  assert.match(p.get("schedule-feedback").textContent, /已有规则可能仍在执行/);
  p.network.fail = false;
  await p.poll();
  assert.equal(p.get("schedule-enabled").disabled, false);
});
