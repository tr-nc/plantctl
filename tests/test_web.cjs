const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");
const settle = () => new Promise((resolve) => setImmediate(resolve));
function page() {
  const elements = new Map(),
    timers = new Map(),
    sockets = [];
  let id = 0,
    poll;
  const status = {
    gateway_online: true,
    automatic_enabled: false,
    schedule_revision: 0,
    fresh: true,
    report: { state: "OFF", power: 0 },
    version: "boot:1",
  };
  const network = { fail: false, reads: 0, manual: [], accepted: [] };
  const listeners = new Map();
  class Socket {
    static OPEN = 1;
    readyState = 1;
    sent = [];
    constructor(url) {
      this.url = url;
      sockets.push(this);
    }
    send(value) {
      this.sent.push(JSON.parse(value));
    }
    close() {
      this.readyState = 3;
      this.onclose?.({ code: 1000 });
    }
    receive(topic, payload = {}) {
      this.onmessage({ data: JSON.stringify({ topic, payload }) });
    }
  }
  const get = (name) => {
    if (!elements.has(name))
      elements.set(name, {
        textContent: "",
        hidden: false,
        disabled: false,
        dataset: {},
        classList: { toggle() {} },
      });
    return elements.get(name);
  };
  vm.runInNewContext(fs.readFileSync("web/app.js", "utf8"), {
    document: { getElementById: get },
    window: {
      addEventListener(name, callback) {
        listeners.set(name, callback);
      },
    },
    location: { protocol: "http:", host: "192.168.50.102" },
    WebSocket: Socket,
    AbortController,
    setTimeout(fn, delay) {
      timers.set(++id, { fn, delay });
      return id;
    },
    clearTimeout(i) {
      timers.delete(i);
    },
    setInterval(fn) {
      poll = fn;
    },
    async fetch(url, options) {
      if (url === "/manual") {
        const value = JSON.parse(options.body);
        network.manual.push(value);
        if (status.automatic_enabled)
          return {
            ok: false,
            status: 409,
            json: async () => ({ error: "请先关闭自动开关" }),
          };
        network.accepted.push(value);
        return { ok: true, status: 200 };
      }
      assert.equal(url, "/device-status");
      network.reads++;
      if (network.fail) throw new Error("offline");
      const data = JSON.parse(JSON.stringify(status));
      return { ok: true, json: async () => data };
    },
  });
  return {
    get,
    timers,
    sockets,
    status,
    network,
    poll: () => poll(),
    mode: (detail) => listeners.get("plantctl:schedule")({ detail }),
  };
}
test("opens without credentials, waits for gateway data, normal UI has no refresh or update text", async () => {
  const p = page();
  await settle();
  assert.equal(p.get("on").disabled, true);
  const ws = p.sockets[0];
  assert.equal(ws.url, "ws://192.168.50.102/api");
  ws.receive("bridge/state");
  await settle();
  assert.equal(p.get("on").disabled, false);
  assert.equal(p.get("feedback").hidden, true);
  assert.equal(ws.sent.length, 0);
  assert.doesNotMatch(
    fs.readFileSync("web/index.html", "utf8"),
    /id="refresh"|type="password"|type="time"/,
  );
});
test("manual command waits for a new matching report; cached values never confirm it", async () => {
  const p = page();
  await settle();
  const ws = p.sockets[0];
  ws.receive("bridge/state");
  await settle();
  p.get("on").onclick();
  assert.deepEqual(p.network.manual, [{ state: "ON" }]);
  assert.equal(ws.sent.length, 0);
  assert.equal(p.get("device-visual").dataset.state, "off");
  assert.equal(p.get("off").disabled, true);
  await p.poll();
  assert.equal(p.get("off").disabled, true);
  p.status.report = { state: "ON", power: 25 };
  p.status.version = "boot:2";
  ws.receive("plant-light");
  await settle();
  assert.equal(p.get("device-visual").dataset.state, "on");
  assert.equal(p.get("off").disabled, false);
  assert.equal(p.get("feedback").hidden, true);
});
test("server freshness and connection determine illustration; automatic recovery requires no query buttons", async () => {
  const p = page();
  await settle();
  const ws = p.sockets[0];
  ws.receive("bridge/state");
  await settle();
  assert.equal(p.get("device-visual").dataset.state, "off");
  p.status.fresh = false;
  p.status.report = {};
  await p.poll();
  assert.equal(p.get("device-visual").dataset.state, "unknown");
  assert.match(p.get("feedback").textContent, /自动查询/);
  p.status.fresh = true;
  p.status.report = { state: "ON" };
  p.status.version = "boot:2";
  await p.poll();
  assert.equal(p.get("device-visual").dataset.state, "on");
  assert.equal(p.get("feedback").hidden, true);
  p.network.fail = true;
  await p.poll();
  assert.equal(p.get("on").disabled, true);
  assert.equal(p.get("device-visual").dataset.state, "unknown");
  p.network.fail = false;
  await p.poll();
  assert.equal(p.get("device-visual").dataset.state, "on");
  ws.close();
  assert.equal(p.get("device-visual").dataset.state, "unknown");
  assert.equal(ws.sent.length, 0);
});
test("timeouts and reconnects report uncertainty without replaying commands", async () => {
  const p = page();
  await settle();
  const ws = p.sockets[0];
  ws.receive("bridge/state");
  await settle();
  p.get("on").onclick();
  [...p.timers.values()].find((t) => t.delay === 15000).fn();
  assert.match(p.get("feedback").textContent, /未收到操作确认/);
  ws.close();
  [...p.timers.values()].find((t) => t.delay === 4000).fn();
  assert.equal(p.sockets.length, 2);
  assert.equal(p.sockets[1].sent.length, 0);
});
test("automatic mode locks manual controls immediately and cannot be reverted by an older status read", async () => {
  const p = page();
  await settle();
  p.sockets[0].receive("bridge/state");
  await settle();
  p.mode({ enabled: false, revision: 0, locked: true });
  assert.equal(p.get("on").disabled, true);
  p.mode({ enabled: true, revision: 1, locked: false });
  await p.poll(); // stale GET still says revision 0 / manual
  assert.equal(p.get("on").disabled, true);
  await p.get("on").onclick();
  assert.equal(p.network.manual.length, 0);
  p.mode({ enabled: false, revision: 2, locked: false });
  assert.equal(p.get("on").disabled, false);
});
test("stale-page manual requests are rejected by the server without dispatch", async () => {
  const p = page();
  await settle();
  p.sockets[0].receive("bridge/state");
  await settle();
  p.status.automatic_enabled = true;
  p.status.schedule_revision = 1;
  await p.get("on").onclick();
  await settle();
  assert.equal(p.network.manual.length, 1);
  assert.equal(p.network.accepted.length, 0);
  assert.equal(p.sockets[0].sent.length, 0);
  assert.equal(p.get("on").disabled, true);
  assert.match(p.get("feedback").textContent, /关闭自动/);
});
test("upstream configuration errors disable controls and retry", async () => {
  const p = page();
  await settle();
  p.sockets[0].onclose({ code: 4401 });
  assert.equal(p.get("on").disabled, true);
  assert.match(p.get("feedback").textContent, /配置异常/);
  [...p.timers.values()].find((t) => t.delay === 4000).fn();
  assert.equal(p.sockets.length, 2);
});
