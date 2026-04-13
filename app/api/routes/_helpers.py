import logging
import re
import subprocess

from flask import Blueprint

log = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

_device_cache: list[dict] | None = None


def _get_devices() -> list[dict]:
    """Return cached device list, probing rtl_test on first call."""
    global _device_cache
    if _device_cache is None:
        _device_cache = _list_rtl_devices()
        if not _device_cache:
            _device_cache = [{"index": 0, "name": "Device 0"}]
    return _device_cache


def _device_name(index: int) -> str:
    for d in _get_devices():
        if d["index"] == index:
            return d["name"]
    return f"Device {index}"


def _list_rtl_devices() -> list[dict]:
    """Return [{index, name}] for each RTL-SDR device found by rtl_test."""
    try:
        result = subprocess.run(
            ["rtl_test"], capture_output=True, text=True, timeout=3
        )
        output = result.stderr + result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    devices: dict[int, str] = {}

    for line in output.splitlines():
        # "  0:  Realtek, RTL2838UHIDIR, SN: 00000001"
        m = re.match(r"^\s+(\d+):\s+.+,\s+(.+),\s+SN:\s+(\S+)", line)
        if m:
            idx, model, serial = int(m.group(1)), m.group(2).strip(), m.group(3)
            devices[idx] = f"{model} (SN: {serial})"

        # "Using device 0: Generic RTL2832U OEM" — the human-readable USB name;
        # overrides the EEPROM model string above when present.
        m = re.match(r"^Using device (\d+):\s+(.+)", line)
        if m:
            devices[int(m.group(1))] = m.group(2).strip()

    return [{"index": k, "name": v} for k, v in sorted(devices.items())]


def _parse_filters(args) -> dict:
    filters = {}
    for key in ("freq_min", "freq_max"):
        val = args.get(key)
        if val is not None and val != "":
            try:
                filters[key] = float(val)
            except ValueError:
                pass
    for key in ("time_min", "time_max"):
        val = args.get(key)
        if val:
            filters[key] = val
    val = args.get("power_min")
    if val is not None and val != "":
        try:
            filters["power_min"] = float(val)
        except ValueError:
            pass
    return filters
