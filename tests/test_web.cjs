const { test } = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");
const fs = require("node:fs");

function page() {
  const elements = new Map();
  const timers = new Map();
  let nextTimer = 0;
  const sockets = [];
  class Socket {
    static OPEN = 1;
    readyState = 1;
    sent = [];
    constructor(url) {
      this.url = url;
      sockets.push(this);
    }
    send(message) {
      this.sent.push(JSON.parse(message));
    }
    close() {
      this.readyState = 3;
      this.onclose?.({ code: 1000 });
    }
    receive(topic, payload) {
      this.onmessage({ data: JSON.stringify({ topic, payload }) });
    }
  }
  const get = (id) => {
    if (!elements.has(id))
      elements.set(id, {
        textContent: "",
        disabled: false,
        dataset: {},
        classList: { toggle() {} },
      });
    return elements.get(id);
  };
  vm.runInNewContext(fs.readFileSync("web/app.js", "utf8"), {
    document: { getElementById: get },
    location: { protocol: "http:", host: "192.168.50.102" },
    WebSocket: Socket,
    Date,
    setTimeout(fn, delay) {
      const id = ++nextTimer;
      timers.set(id, { fn, delay });
      return id;
    },
    clearTimeout(id) {
      timers.delete(id);
    },
  });
  return { get, sockets, timers };
}
test("opens automatically without credentials; controls wait for gateway data", () => {
  const p = page(),
    ws = p.sockets[0];
  assert.equal(p.sockets.length, 1);
  assert.equal(ws.url, "ws://192.168.50.102/api");
  assert.equal(p.get("on").disabled, true);
  assert.equal(ws.sent.length, 0);
  ws.receive("bridge/state", { state: "online" });
  assert.equal(p.get("on").disabled, false);
  assert.doesNotMatch(
    fs.readFileSync("web/index.html", "utf8"),
    /type="password"|login-form/,
  );
});
test("explicit commands wait for matching state and never update optimistically", () => {
  const p = page(),
    ws = p.sockets[0];
  ws.receive("bridge/state", { state: "online" });
  ws.receive("plant-light", { state: "OFF", power: 0 });
  p.get("on").onclick();
  assert.deepEqual(ws.sent, [
    { topic: "plant-light/set", payload: { state: "ON" } },
  ]);
  assert.match(p.get("state-badge").textContent, /已关闭/);
  assert.equal(p.get("off").disabled, true);
  ws.receive("plant-light", { power: 5 });
  assert.equal(p.get("off").disabled, true);
  ws.receive("plant-light", { state: "ON" });
  assert.equal(p.get("off").disabled, false);
  assert.match(p.get("feedback").textContent, /已更新/);
  p.get("off").onclick();
  assert.deepEqual(ws.sent[1], {
    topic: "plant-light/set",
    payload: { state: "OFF" },
  });
});
test("query, timeout, offline and reconnection do not replay commands", () => {
  const p = page(),
    ws = p.sockets[0];
  ws.receive("bridge/state", { state: "online" });
  p.get("refresh").onclick();
  assert.deepEqual(ws.sent[0], {
    topic: "plant-light/get",
    payload: { state: "" },
  });
  [...p.timers.values()].find((t) => t.delay === 12000).fn();
  assert.match(p.get("feedback").textContent, /暂未收到/);
  ws.receive("bridge/state", { state: "offline" });
  assert.equal(p.get("on").disabled, true);
  ws.close();
  [...p.timers.values()].find((t) => t.delay === 4000).fn();
  assert.equal(p.sockets.length, 2);
  assert.equal(p.sockets[1].url, "ws://192.168.50.102/api");
  assert.equal(p.sockets[1].sent.length, 0);
});
test("illustration follows reported state, never optimistic clicks or stale disconnected state", () => {
  const p = page(),
    ws = p.sockets[0];
  assert.equal(p.get("device-visual").dataset.state, "unknown");
  ws.receive("plant-light", { state: "ON" });
  assert.equal(p.get("device-visual").dataset.state, "unknown");
  ws.receive("bridge/state", { state: "online" });
  assert.equal(p.get("device-visual").dataset.state, "on");
  p.get("off").onclick();
  assert.equal(p.get("device-visual").dataset.state, "on");
  ws.receive("plant-light", { state: "OFF" });
  assert.equal(p.get("device-visual").dataset.state, "off");
  ws.receive("bridge/state", { state: "offline" });
  assert.equal(p.get("device-visual").dataset.state, "unknown");
  ws.close();
  assert.equal(p.get("device-visual").dataset.state, "unknown");
});
test("upstream credential failure disables controls and retries without asking for a password", () => {
  const p = page(),
    ws = p.sockets[0];
  ws.onclose({ code: 4401 });
  assert.equal(p.get("on").disabled, true);
  assert.match(p.get("feedback").textContent, /配置异常/);
  [...p.timers.values()].find((t) => t.delay === 4000).fn();
  assert.equal(p.sockets.length, 2);
  assert.equal(p.sockets[1].sent.length, 0);
});
