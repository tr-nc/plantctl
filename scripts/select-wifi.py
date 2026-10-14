#!/usr/bin/env python3
"""Select nearby Wi-Fi locally; return only the path to a private credentials file."""

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


class Cancelled(Exception):
    """The user cancelled without saving credentials."""


@dataclass(frozen=True)
class Network:
    ssid: str
    band: str
    signal: int
    security: str


def run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        env={**os.environ, "LC_ALL": "C.UTF-8"},
        capture_output=True,
        text=True,
        check=False,
    )


def dialog(arguments: list[str]) -> str:
    result = run(["zenity", *arguments])
    if result.returncode == 1:
        raise Cancelled
    if result.returncode != 0:
        raise RuntimeError("无法打开输入窗口。请在本机图形桌面下运行。")
    return result.stdout.removesuffix("\n")


def message(kind: str, text: str) -> None:
    result = run(["zenity", f"--{kind}", f"--text={text}"])
    if result.returncode not in {0, 1}:
        raise RuntimeError("无法打开提示窗口。")


def split_nmcli(line: str) -> list[str]:
    """Decode nmcli's escaped colon-separated fields, including literal backslashes."""
    fields: list[str] = []
    field: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            field.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            fields.append("".join(field))
            field = []
        else:
            field.append(char)
    if escaped:
        field.append("\\")
    return [*fields, "".join(field)]


def select_interface(requested: str | None) -> str:
    result = run(
        ["nmcli", "-t", "--escape", "yes", "-f", "DEVICE,TYPE", "device", "status"]
    )
    if result.returncode != 0:
        raise RuntimeError("无法访问 NetworkManager。请确认服务正在运行。")
    interfaces = []
    for line in result.stdout.splitlines():
        fields = split_nmcli(line)
        if len(fields) == 2 and fields[1] == "wifi":
            interfaces.append(fields[0])
    if requested is not None:
        if requested not in interfaces:
            raise RuntimeError(
                "指定的接口不是可用无线网卡。请用 nmcli device status 检查。"
            )
        return requested
    if not interfaces:
        raise RuntimeError("没有找到无线网卡。请检查电脑是否具有可用的 Wi-Fi 硬件。")
    if len(interfaces) != 1:
        raise RuntimeError("检测到多张无线网卡，请用 --interface 指定要扫描的接口。")
    return interfaces[0]


def scan_networks(interface: str, band_filter: str) -> list[Network]:
    result = run(
        [
            "nmcli",
            "-t",
            "--escape",
            "yes",
            "-f",
            "SSID,FREQ,SIGNAL,SECURITY",
            "device",
            "wifi",
            "list",
            "ifname",
            interface,
            "--rescan",
            "yes",
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(
            "无法扫描 Wi-Fi。请用 nmcli radio wifi 检查无线功能是否启用。"
        )
    networks: dict[tuple[str, str, str], Network] = {}
    for line in result.stdout.splitlines():
        fields = split_nmcli(line)
        if len(fields) != 4:
            continue
        ssid, frequency, signal, security = fields
        if not ssid or not 1 <= len(ssid.encode("utf-8")) <= 32 or "\x00" in ssid:
            continue
        try:
            mhz = int(frequency.split()[0])
            strength = int(signal)
        except (ValueError, IndexError):
            continue
        if 2400 <= mhz <= 2500:
            band = "2.4"
        elif 4900 <= mhz < 5925:
            band = "5"
        else:
            continue
        if band_filter != "all" and band != band_filter:
            continue
        key = (ssid, band, security)
        old = networks.get(key)
        if old is None or strength > old.signal:
            networks[key] = Network(ssid, band, strength, security)
    return sorted(networks.values(), key=lambda network: -network.signal)


def security_mode(security: str) -> str:
    if security in {"", "--"}:
        return "none"
    if any(value in security for value in ("802.1X", "WEP", "OWE")):
        raise ValueError("这个网络不是普通密码型家用 Wi-Fi，需要另行配置。")
    if "WPA3" in security and "WPA2" not in security and "WPA1" not in security:
        return "sae"
    if "WPA" in security:
        return "psk"
    raise ValueError("无法识别这个网络的安全模式，请选择其他网络。")


def password_valid(password: str, mode: str) -> bool:
    if any(char in password for char in ("\x00", "\n", "\r")):
        return False
    if mode == "sae":
        return 1 <= len(password.encode("utf-8")) <= 63
    return (
        8 <= len(password.encode("utf-8")) <= 63
        or re.fullmatch(r"[0-9a-fA-F]{64}", password) is not None
    )


def collect(networks: list[Network], country: str) -> dict[str, str | bool | int]:
    rows = []
    for index, network in enumerate(networks):
        rows.extend(
            [
                str(index),
                network.ssid,
                f"{network.band} GHz",
                f"{network.signal}%",
                network.security,
            ]
        )
    while True:
        selection = dialog(
            [
                "--list",
                "--title=选择 Wi-Fi",
                f"--text=选择 Wi-Fi 后只需输入密码；不会切换电脑的网络连接。\n同名双频网络不锁定频段；地区码：{country}。",
                "--width=820",
                "--height=540",
                "--column=编号",
                "--column=Wi-Fi 名称",
                "--column=频段",
                "--column=信号",
                "--column=安全模式",
                "--hide-column=1",
                "--print-column=1",
                "--ok-label=选择并继续",
                "--cancel-label=取消",
                "--",
                *rows,
            ]
        )
        try:
            index = int(selection)
            if not 0 <= index < len(networks):
                raise ValueError
            network = networks[index]
        except ValueError:
            continue
        try:
            mode = security_mode(network.security)
        except ValueError as error:
            message("error", str(error))
            continue
        if mode == "none":
            try:
                dialog(
                    [
                        "--question",
                        "--title=确认开放网络",
                        f"--text=网络 {html.escape(network.ssid)} 没有密码，通信可能不受保护。仍要使用吗？",
                    ]
                )
            except Cancelled:
                continue
            password = ""
        else:
            while True:
                password = dialog(
                    [
                        "--password",
                        "--title=输入 Wi-Fi 密码",
                        f"--text=Wi-Fi：{html.escape(network.ssid)}\n密码只在本机处理，不输出到终端。\n保存的配置包含明文密码，请保管好并在使用后删除。",
                        "--ok-label=保存配置",
                        "--cancel-label=取消",
                    ]
                )
                if password_valid(password, mode):
                    break
                message("error", "密码格式无效，请重新填写。")
        return {
            "version": 1,
            "ssid": network.ssid,
            "password": password,
            "mode": mode,
            "country": country,
            "hidden": False,
        }


def save_credentials(details: dict[str, str | bool | int]) -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    directory = Path(runtime) if runtime else Path(tempfile.gettempdir())
    fd, filename = tempfile.mkstemp(
        prefix="plantctl-wifi-", suffix=".json", dir=directory
    )
    path = Path(filename)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(details, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def country_code(value: str) -> str:
    value = value.upper()
    if re.fullmatch(r"[A-Z]{2}|00", value) is None:
        raise argparse.ArgumentTypeError("地区码须为两个英文字母或 00，例如 CN、US。")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="在 Linux 桌面上扫描并选择 Wi-Fi，输入密码后保存到私有临时 JSON 文件。",
        epilog="只输出文件路径，不输出密码。不写 TF 卡、不连接网络。取消返回 130。例：%(prog)s --band 2.4",
    )
    parser.add_argument("--interface", help="扫描用无线网卡；只有一张时自动选择")
    parser.add_argument(
        "--band",
        choices=("all", "2.4", "5"),
        default="all",
        help="列表频段过滤，不锁定连接频段（默认 all）",
    )
    parser.add_argument(
        "--country",
        type=country_code,
        default="CN",
        help="目标设备的无线地区码（默认 CN）",
    )
    args = parser.parse_args()
    try:
        if os.geteuid() == 0:
            raise RuntimeError("请以普通桌面用户运行，不要使用 sudo。")
        for tool in ("nmcli", "zenity"):
            if shutil.which(tool) is None:
                raise RuntimeError(
                    "需要 nmcli 和 zenity。Fedora 可运行：sudo dnf install NetworkManager zenity"
                )
        interface = select_interface(args.interface)
        networks = scan_networks(interface, args.band)
        if not networks:
            raise RuntimeError(
                "没有扫描到所选频段的可见 Wi-Fi。请检查路由器，或换用 --band all。"
            )
        path = save_credentials(collect(networks, args.country))
        print(path)
        return 0
    except (Cancelled, KeyboardInterrupt):
        print("已取消，未保存 Wi-Fi 配置。", file=sys.stderr)
        return 130
    except (RuntimeError, OSError) as error:
        # Never echo subprocess output or credentials when reporting failures.
        text = (
            str(error)
            if isinstance(error, RuntimeError)
            else "无法运行工具或保存私有临时文件。请检查桌面会话和临时目录。"
        )
        print(f"错误：{text}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
