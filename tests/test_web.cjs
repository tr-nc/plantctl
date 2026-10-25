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
    fresh: true,
    report: { state: "OFF", power: 0 },
    version: "boot:1",
  };
  const network = { fail: false, reads: 0 };
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
    async fetch(url) {
      assert.equal(url, "/device-status");
      network.reads++;
      if (network.fail) throw new Error("offline");
      const data = JSON.parse(JSON.stringify(status));
      return { ok: true, json: async () => data };
    },
  });
  return { get, timers, sockets, status, network, poll: () => poll() };
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
  assert.deepEqual(ws.sent, [
    { topic: "plant-light/set", payload: { state: "ON" } },
  ]);
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
test("upstream configuration errors disable controls and retry", async () => {
  const p = page();
  await settle();
  p.sockets[0].onclose({ code: 4401 });
  assert.equal(p.get("on").disabled, true);
  assert.match(p.get("feedback").textContent, /配置异常/);
  [...p.timers.values()].find((t) => t.delay === 4000).fn();
  assert.equal(p.sockets.length, 2);
});
