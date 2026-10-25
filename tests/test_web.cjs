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
        value: "",
        textContent: "",
        hidden: false,
        disabled: false,
        classList: { toggle() {} },
        addEventListener(event, fn) {
          this[event] = fn;
        },
      });
    return elements.get(id);
  };
  vm.runInNewContext(fs.readFileSync("web/app.js", "utf8"), {
    document: { getElementById: get },
    location: { protocol: "http:", host: "192.168.50.102" },
    WebSocket: Socket,
    Intl,
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
  const login = () => {
    get("password").value = "test-secret";
    get("login-form").submit({ preventDefault() {} });
    return sockets.at(-1);
  };
  return { get, login, sockets, timers };
}
test("controls require protected data, not just a WebSocket upgrade", () => {
  const p = page(),
    ws = p.login();
  assert.equal(p.get("on").disabled, true);
  assert.equal(ws.sent.length, 0);
  ws.receive("bridge/state", { state: "online" });
  assert.equal(p.get("on").disabled, false);
  assert.equal(p.get("password").value, "");
});
test("explicit commands are unretained, pending until matching report; never optimistic", () => {
  const p = page(),
    ws = p.login();
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
  assert.match(p.get("feedback").textContent, /收到设备状态/);
});
test("query, timeout, offline and reconnection do not replay commands", () => {
  const p = page(),
    ws = p.login();
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
  assert.equal(p.sockets[1].sent.length, 0);
});
test("bad password restores login; logout discards state and cancels retries", () => {
  const p = page(),
    ws = p.login();
  ws.onclose({ code: 4401 });
  assert.equal(p.get("login").hidden, false);
  assert.equal(p.get("on").disabled, true);
  assert.equal(
    [...p.timers.values()].filter((t) => t.delay === 4000).length,
    0,
  );
  const good = p.login();
  good.receive("bridge/state", { state: "online" });
  good.receive("plant-light", { state: "ON", power: 42 });
  p.get("logout").onclick();
  assert.equal(p.get("power").textContent, "—");
  assert.equal(p.get("on").disabled, true);
  assert.equal(p.timers.size, 0);
});
