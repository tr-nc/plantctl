const DAY = 1440;
export const STEP = 30;
export const wrap = (value) => ((value % DAY) + DAY) % DAY;
export const snap = (value) => wrap(Math.round(value / STEP) * STEP);
export function toMinutes(value) {
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value))
    throw new Error("Invalid time");
  const [hour, minute] = value.split(":").map(Number);
  return hour * 60 + minute;
}
export function toTime(value) {
  const minute = wrap(value);
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}
export const duration = (on, off) => wrap(off - on);
export function point(value, radius = 116) {
  const angle = (value / DAY) * Math.PI * 2 - Math.PI / 2;
  return {
    x: 160 + radius * Math.cos(angle),
    y: 160 + radius * Math.sin(angle),
  };
}
export function timeAt(x, y) {
  return snap(
    ((Math.atan2(y - 160, x - 160) + Math.PI / 2) * DAY) / (Math.PI * 2),
  );
}
export function arcPath(on, off) {
  const a = point(on),
    b = point(off);
  return `M ${a.x} ${a.y} A 116 116 0 ${duration(on, off) > 720 ? 1 : 0} 1 ${b.x} ${b.y}`;
}

export class ScheduleDial {
  constructor(root, onChange, onCommit = () => {}) {
    this.root = root;
    this.onChange = onChange;
    this.onCommit = onCommit;
    this.values = { on: 480, off: 1320 };
    this.active = "on";
    this.disabled = true;
    this.drag = null;
    this.handles = {};
    this.picks = {};
    for (const edge of ["on", "off"]) {
      this.handles[edge] = root.querySelector(`[data-edge="${edge}"]`);
      this.picks[edge] = root.parentElement.querySelector(
        `[data-pick="${edge}"]`,
      );
      this.picks[edge].addEventListener("click", () => this.select(edge));
      this.handles[edge].addEventListener("keydown", (event) => {
        if (this.disabled) return;
        const direction = {
          ArrowRight: 1,
          ArrowUp: 1,
          ArrowLeft: -1,
          ArrowDown: -1,
          PageUp: 2,
          PageDown: -2,
        }[event.key];
        if (direction || ["Home", "End"].includes(event.key)) {
          event.preventDefault();
          this.select(edge);
          const value =
            event.key === "Home"
              ? 0
              : event.key === "End"
                ? 1410
                : snap(this.values[edge]) + direction * STEP;
          const previous = this.values[edge];
          this.change(edge, value);
          if (previous !== this.values[edge]) this.onCommit("keyboard");
        }
      });
    }
    const ticks = root.querySelector(".dial-ticks");
    for (let minute = 0; minute < DAY; minute += STEP) {
      const a = point(minute, minute % 360 === 0 ? 91 : 95),
        b = point(minute, 99);
      const line = document.createElementNS(
        "http://www.w3.org/2000/svg",
        "line",
      );
      for (const [key, value] of Object.entries({
        x1: a.x,
        y1: a.y,
        x2: b.x,
        y2: b.y,
      }))
        line.setAttribute(key, value);
      ticks.append(line);
    }
    root.addEventListener("pointerdown", (event) => this.start(event));
    root.addEventListener("pointermove", (event) => this.move(event));
    root.addEventListener("pointerup", (event) => this.end(event));
    root.addEventListener("pointercancel", (event) => this.cancel(event));
    root.addEventListener("lostpointercapture", (event) => this.cancel(event));
    this.render();
  }
  get times() {
    return { on: toTime(this.values.on), off: toTime(this.values.off) };
  }
  setRange(on, off) {
    this.drag = null;
    this.values = { on: toMinutes(on), off: toMinutes(off) };
    this.render();
  }
  setDisabled(disabled) {
    if (disabled && this.drag) {
      this.values = this.drag.original;
      this.drag = null;
      this.render();
    }
    this.disabled = disabled;
    this.root.setAttribute("aria-disabled", String(disabled));
    for (const edge of ["on", "off"])
      this.handles[edge].disabled = this.picks[edge].disabled = disabled;
  }
  select(edge) {
    this.active = edge;
    this.render();
  }
  change(edge, value) {
    value = snap(value);
    if (
      value === this.values[edge === "on" ? "off" : "on"] ||
      value === this.values[edge]
    )
      return;
    this.values[edge] = value;
    this.render();
    this.onChange();
  }
  position(event) {
    const box = this.root.getBoundingClientRect();
    return {
      x: ((event.clientX - box.left) * 320) / box.width,
      y: ((event.clientY - box.top) * 320) / box.height,
    };
  }
  start(event) {
    if (
      this.disabled ||
      this.drag ||
      event.isPrimary === false ||
      event.button !== 0
    )
      return;
    const handle = event.target.closest("[data-edge]");
    const p = this.position(event),
      radius = Math.hypot(p.x - 160, p.y - 160);
    if (!handle && (radius < 100 || radius > 142)) return;
    event.preventDefault();
    const edge = handle?.dataset.edge || this.active;
    this.select(edge);
    this.drag = {
      id: event.pointerId,
      edge,
      original: { ...this.values },
      x: event.clientX,
      y: event.clientY,
      moved: false,
      track: !handle,
    };
    this.root.setPointerCapture(event.pointerId);
    this.handles[edge].focus({ preventScroll: true });
  }
  move(event) {
    if (!this.drag || event.pointerId !== this.drag.id || this.disabled) return;
    if (
      Math.hypot(event.clientX - this.drag.x, event.clientY - this.drag.y) <
        3 &&
      !this.drag.moved
    )
      return;
    this.drag.moved = true;
    const p = this.position(event);
    // Keep the value stable when a finger passes through the ambiguous centre.
    if (Math.hypot(p.x - 160, p.y - 160) >= 40)
      this.change(this.drag.edge, timeAt(p.x, p.y));
  }
  end(event) {
    if (!this.drag || event.pointerId !== this.drag.id) return;
    if (!this.disabled && (this.drag.track || this.drag.moved)) {
      const p = this.position(event);
      if (Math.hypot(p.x - 160, p.y - 160) >= 40)
        this.change(this.drag.edge, timeAt(p.x, p.y));
    }
    const changed =
      this.drag.original.on !== this.values.on ||
      this.drag.original.off !== this.values.off;
    this.drag = null;
    this.root.releasePointerCapture(event.pointerId);
    if (!this.disabled && changed) this.onCommit("pointer");
  }
  cancel(event) {
    if (!this.drag || event.pointerId !== this.drag.id) return;
    this.values = this.drag.original;
    this.drag = null;
    this.render();
    this.onChange();
  }
  render() {
    this.root
      .querySelector(".dial-arc")
      .setAttribute("d", arcPath(this.values.on, this.values.off));
    for (const edge of ["on", "off"]) {
      const handle = this.handles[edge],
        p = point(this.values[edge]);
      handle.style.left = `${p.x / 3.2}%`;
      handle.style.top = `${p.y / 3.2}%`;
      handle.classList.toggle("selected", this.active === edge);
      handle.setAttribute("aria-valuenow", this.values[edge]);
      handle.setAttribute("aria-valuetext", toTime(this.values[edge]));
      this.picks[edge].setAttribute(
        "aria-pressed",
        String(this.active === edge),
      );
      this.picks[edge].querySelector("strong").textContent = toTime(
        this.values[edge],
      );
    }
    this.root.querySelector(".dial-duration").textContent =
      `${duration(this.values.on, this.values.off) / 60} 小时`;
  }
}
