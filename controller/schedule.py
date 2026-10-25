"""Daily light schedule: persistence and transition ownership live here."""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Asia/Shanghai")


class ConflictError(ValueError):
    pass


@dataclass(frozen=True)
class Plan:
    enabled: bool = False
    on: str = "08:00"
    off: str = "22:00"
    revision: int = 0

    @classmethod
    def parse(cls, value: object) -> Plan:
        if not isinstance(value, dict) or set(value) != {
            "enabled",
            "on",
            "off",
            "revision",
        }:
            raise ValueError("需要完整的 enabled、on、off、revision 配置。")
        if type(value["enabled"]) is not bool:
            raise ValueError("自动开关必须为布尔值。")
        for field in ("on", "off"):
            if not isinstance(value[field], str) or not re.fullmatch(
                r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value[field]
            ):
                raise ValueError("时间格式必须为 HH:MM。")
        if value["on"] == value["off"]:
            raise ValueError("开启和关闭时间不能相同。")
        if type(value["revision"]) is not int or value["revision"] < 0:
            raise ValueError("配置版本无效，请刷新后重试。")
        return cls(**value)


def transitions(
    plan: Plan, now: datetime
) -> tuple[tuple[datetime, str], tuple[datetime, str]]:
    """Most recent and next edges; handles midnight and missed transitions."""
    now = now.astimezone(ZONE)
    edges = []
    for delta in (-1, 0, 1):
        day = now.date() + timedelta(days=delta)
        for clock, state in ((plan.on, "ON"), (plan.off, "OFF")):
            hour, minute = map(int, clock.split(":"))
            edges.append(
                (
                    datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZONE),
                    state,
                )
            )
    return max(edge for edge in edges if edge[0] <= now), min(
        edge for edge in edges if edge[0] > now
    )


class Gateway(Protocol):
    @property
    def online(self) -> bool: ...

    def set_state(self, state: str) -> bool:
        """Return whether submitted to the broker, not whether the device acted."""
        ...


class Scheduler:
    def __init__(
        self,
        path: Path,
        gateway: Gateway,
        now: Callable[[], datetime],
        clock_ready: Callable[[], bool],
    ) -> None:
        self.path = path
        self.gateway = gateway
        self.now = now
        self.clock_ready = clock_ready
        self.lock = threading.RLock()
        # Corrupt data is an error, never silently replace it with defaults.
        self.plan = (
            Plan.parse(json.loads(path.read_text())) if path.exists() else Plan()
        )
        self.applied: tuple[datetime, str] | None = None
        self.last_action: dict | None = None

    def snapshot(self) -> dict:
        with self.lock:
            following = (
                transitions(self.plan, self.now())[1] if self.plan.enabled else None
            )
            return {
                **asdict(self.plan),
                "timezone": "Asia/Shanghai",
                "next": {"at": following[0].isoformat(), "state": following[1]}
                if following
                else None,
                "clock_ready": self.clock_ready(),
                "gateway_online": self.gateway.online,
                "last_action": self.last_action,
            }

    def save(self, value: object) -> dict:
        candidate = Plan.parse(value)
        with self.lock:
            if candidate.revision != self.plan.revision:
                raise ConflictError("配置已被其他设备修改，请重新加载后再保存。")
            if candidate == self.plan:
                return self.snapshot()
            candidate = replace(candidate, revision=self.plan.revision + 1)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".schedule-")
            try:
                with os.fdopen(fd, "w") as output:
                    json.dump(asdict(candidate), output)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, self.path)
                directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            # Never activate an unsaved plan. Serialize save/disable with dispatch.
            self.plan = candidate
            self.applied = None
            self.last_action = None
            return self.snapshot()

    def manual(self, value: object) -> dict:
        if (
            not isinstance(value, dict)
            or set(value) != {"state"}
            or value["state"] not in ("ON", "OFF")
        ):
            raise ValueError("手动状态必须为 ON 或 OFF。")
        with self.lock:
            # The same lock owns mode changes and dispatch, so a stale browser
            # cannot race an enabled schedule with an unguarded manual command.
            if self.plan.enabled:
                raise ConflictError("请先关闭自动开关，再手动控制。")
            if not self.gateway.online or not self.gateway.set_state(value["state"]):
                raise ConnectionError("网关暂不可用，指令未确认提交。")
            return {"result": "sent", "state": value["state"]}

    def tick(self) -> None:
        with self.lock:
            if not self.plan.enabled or not self.clock_ready():
                return
            edge, _ = transitions(self.plan, self.now())
            if edge == self.applied or not self.gateway.online:
                return
            if self.gateway.set_state(edge[1]):
                self.applied = edge
                self.last_action = {
                    "at": self.now().isoformat(),
                    "state": edge[1],
                    "result": "sent",
                }
            # After broker submission, do not replay. Offline edges collapse
            # to the current desired state; dashboard manual control is gated.
