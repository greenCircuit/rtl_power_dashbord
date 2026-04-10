"""
BandCaptureManager — one RTLPowerCapture per device_index.
Multiple bands on the same device are scanned in a single rtl_power process
using multiple -f flags; the process hops between them automatically.
"""

import logging
import threading

from app.capture.rtl_power import RTLPowerCapture
from app.data import db

log = logging.getLogger(__name__)


class BandCaptureManager:
    def __init__(self):
        # device_index -> {band_id -> band dict}
        self._active: dict[int, dict[str, dict]] = {}
        # device_index -> RTLPowerCapture
        self._captures: dict[int, RTLPowerCapture] = {}
        self._lock = threading.Lock()

    # ── public API ────────────────────────────────────────────────────────────

    def start_band(self, band_id: str) -> None:
        band = db.get_band(band_id)
        if not band:
            raise ValueError(f"Band {band_id!r} not found")
        device = band["device_index"]
        with self._lock:
            if band_id in self._active.get(device, {}):
                raise RuntimeError(f"'{band['name']}' is already capturing")
            self._active.setdefault(device, {})[band_id] = band
            self._restart_device(device)

    def stop_band(self, band_id: str) -> None:
        with self._lock:
            for device, bands in self._active.items():
                if band_id in bands:
                    del bands[band_id]
                    log.info("Stopping band [%s] on device %d", band_id, device)
                    self._restart_device(device)
                    return

    def start_active_bands(self, bands: list[dict]) -> None:
        """Start a list of bands grouped by device — one process per device."""
        by_device: dict[int, list[dict]] = {}
        for b in bands:
            by_device.setdefault(b["device_index"], []).append(b)
        with self._lock:
            for device, device_bands in by_device.items():
                for b in device_bands:
                    self._active.setdefault(device, {})[b["id"]] = b
                self._restart_device(device)

    def get_status(self, band_id: str) -> str:
        for device, bands in self._active.items():
            if band_id in bands:
                cap = self._captures.get(device)
                return cap.status if cap else "idle"
        return "idle"

    def get_error(self, band_id: str) -> str | None:
        for device, bands in self._active.items():
            if band_id in bands:
                cap = self._captures.get(device)
                return cap.error if cap else None
        return None

    def all_statuses(self) -> dict[str, str]:
        result = {}
        for device, bands in self._active.items():
            cap = self._captures.get(device)
            status = cap.status if cap else "idle"
            for band_id in bands:
                result[band_id] = status
        return result

    # ── internal ──────────────────────────────────────────────────────────────

    def _restart_device(self, device_index: int) -> None:
        """Stop the current capture for a device and restart with all active bands."""
        cap = self._captures.get(device_index)
        if cap:
            cap.stop()

        bands = list(self._active.get(device_index, {}).values())
        if not bands:
            self._captures.pop(device_index, None)
            log.info("Device %d has no active bands — capture stopped", device_index)
            return

        band_names = ", ".join(b["name"] for b in bands)
        log.info("Starting device %d with %d band(s): %s", device_index, len(bands), band_names)
        cap = RTLPowerCapture()
        try:
            cap.start(bands, device_index)
        except RuntimeError:
            pass
        self._captures[device_index] = cap


band_manager = BandCaptureManager()
