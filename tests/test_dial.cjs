const { test } = require("node:test");
const assert = require("node:assert/strict");
const modulePromise = import("../web/dial.mjs");
function node() {
  return {
    style: {},
    attrs: {},
    events: {},
    classList: { toggle() {} },
    textContent: "",
    disabled: false,
    setAttribute(k, v) {
      this.attrs[k] = String(v);
    },
    addEventListener(k, v) {
      this.events[k] = v;
    },
    append() {},
    focus() {},
  };
}
async function widget() {
  const { ScheduleDial, point } = await modulePromise;
  const nodes = Object.fromEntries(
    ["on", "off", "pick-on", "pick-off", "arc", "ticks", "duration"].map(
      (k) => [k, node()],
    ),
  );
  for (const edge of ["on", "off"]) {
    nodes[edge].dataset = { edge };
    nodes[edge].closest = () => nodes[edge];
    nodes["pick-" + edge].querySelector = () => nodes["pick-" + edge];
  }
  const root = node();
  root.querySelector = (s) =>
    s.includes("data-edge")
      ? nodes[s.includes('"on"') ? "on" : "off"]
      : nodes[
          {
            ".dial-arc": "arc",
            ".dial-ticks": "ticks",
            ".dial-duration": "duration",
          }[s]
        ];
  root.parentElement = {
    querySelector: (s) => nodes[s.includes('"on"') ? "pick-on" : "pick-off"],
  };
  root.getBoundingClientRect = () => ({
    left: 0,
    top: 0,
    width: 320,
    height: 320,
  });
  root.setPointerCapture = () => {};
  root.releasePointerCapture = () => {};
  global.document = { createElementNS: () => node() };
  let changes = 0;
  const dial = new ScheduleDial(root, () => changes++);
  delete global.document;
  dial.setDisabled(false);
  const event = (time, target = nodes.on, id = 1) => ({
    pointerId: id,
    button: 0,
    isPrimary: true,
    clientX: point(time).x,
    clientY: point(time).y,
    target,
    preventDefault() {},
  });
  return { dial, nodes, event, changes: () => changes };
}
test("24-hour cardinal positions and every half-hour round-trip", async () => {
  const { point, timeAt, snap, toTime, toMinutes } = await modulePromise;
  for (let m = 0; m < 1440; m += 30) {
    const p = point(m);
    assert.equal(timeAt(p.x, p.y), m);
    assert.equal(toMinutes(toTime(m)), m);
  }
  assert.equal(timeAt(160, 0), 0);
  assert.equal(timeAt(320, 160), 360);
  assert.equal(timeAt(160, 320), 720);
  assert.equal(timeAt(0, 160), 1080);
  assert.equal(snap(1439), 0);
  assert.equal(snap(-30), 1410);
});
test("clockwise arc expresses daytime, overnight and half-hour ranges", async () => {
  const { duration, arcPath } = await modulePromise;
  assert.equal(duration(480, 1320), 840);
  assert.match(arcPath(480, 1320), /116 116 0 1 1/);
  assert.equal(duration(1200, 360), 600);
  assert.match(arcPath(1200, 360), /116 116 0 0 1/);
  assert.equal(duration(1410, 0), 30);
});
test("endpoints keep meaning across midnight, never coincide; legacy minutes preserved until edited", async () => {
  const { dial, changes, nodes } = await widget();
  dial.setRange("23:30", "06:00");
  dial.change("on", 0);
  assert.deepEqual(dial.times, { on: "00:00", off: "06:00" });
  dial.change("on", 360);
  assert.equal(dial.times.on, "00:00");
  assert.equal(changes(), 1);
  dial.setRange("08:05", "22:00");
  assert.equal(dial.times.on, "08:05");
  assert.equal(nodes.on.attrs["aria-valuetext"], "08:05");
  dial.change("on", 500);
  assert.equal(dial.times.on, "08:30");
});
test("drag previews, pointer cancellation rolls back, track taps and keyboard need no typing", async () => {
  const { dial, event, nodes } = await widget();
  dial.start(event(480));
  dial.move(event(600));
  assert.equal(dial.times.on, "10:00");
  dial.cancel(event(600));
  assert.equal(dial.times.on, "08:00");
  dial.start(event(480));
  dial.move(event(630));
  dial.end(event(630));
  assert.equal(dial.times.on, "10:30");
  dial.select("off");
  const track = { closest: () => null };
  dial.start(event(1200, track));
  dial.end(event(1200, track));
  assert.equal(dial.times.off, "20:00");
  nodes.off.events.keydown({ key: "ArrowRight", preventDefault() {} });
  assert.equal(dial.times.off, "20:30");
  dial.setDisabled(true);
  dial.start(event(60));
  assert.equal(dial.drag, null);
});
