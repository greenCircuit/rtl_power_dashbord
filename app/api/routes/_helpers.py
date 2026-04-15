import logging
import re
import subprocess

from flask import Blueprint

from app.data.db import GRANULARITY_SECONDS

log = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

# Derived from the DB layer's GRANULARITY_SECONDS so the two can never diverge.
VALID_GRANULARITIES = frozenset(GRANULARITY_SECONDS)

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


def _parse_float_arg(args, name: str, default: float) -> float:
    """Return a float query param. Raise ValueError with a descriptive message on bad input."""
    val = args.get(name)
    if val is None or val == "":
        return default
    try:
        return float(val)
    except ValueError:
        raise ValueError(f"'{name}' must be a number, got {val!r}")


def _parse_int_arg(
    args, name: str, default: int,
    min_val: int | None = None, max_val: int | None = None,
) -> int:
    """Return an int query param with optional bounds. Raise ValueError on bad input."""
    val = args.get(name)
    if val is None or val == "":
        return default
    try:
        result = int(val)
    except ValueError:
        raise ValueError(f"'{name}' must be an integer, got {val!r}")
    if min_val is not None and result < min_val:
        raise ValueError(f"'{name}' must be >= {min_val}, got {result}")
    if max_val is not None and result > max_val:
        raise ValueError(f"'{name}' must be <= {max_val}, got {result}")
    return result


def _parse_granularity(args, default: str = "1h") -> str:
    """Return a validated granularity query param. Raise ValueError for unknown values."""
    val = args.get("granularity", default)
    if val not in VALID_GRANULARITIES:
        raise ValueError(
            f"'granularity' must be one of {sorted(VALID_GRANULARITIES)}, got {val!r}"
        )
    return val


def _parse_filters(args) -> dict:
    filters = {}
    for key in ("freq_min", "freq_max"):
        val = args.get(key)
        if val is not None and val != "":
            try:
                filters[key] = float(val)
            except ValueError:
                raise ValueError(f"'{key}' must be a number, got {val!r}")
    for key in ("time_min", "time_max"):
        val = args.get(key)
        if val:
            filters[key] = val
    val = args.get("power_min")
    if val is not None and val != "":
        try:
            filters["power_min"] = float(val)
        except ValueError:
            raise ValueError(f"'power_min' must be a number, got {val!r}")
    return filters
