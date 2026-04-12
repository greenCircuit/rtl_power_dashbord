"""
BandCaptureManager — one RTLPowerCapture per device at a time.

rtl_power only reliably outputs data for the LAST -f range when multiple
non-contiguous ranges are given.  To work around this, each band gets its
own rtl_power process.  On devices with more than one active band the
manager cycles through them: band A runs for interval_s seconds, then band B,
then band C, etc.  Every band is served; each just scans every
(num_bands × interval_s) seconds instead of every interval_s.
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
        # device_index -> current RTLPowerCapture
        self._captures: dict[int, RTLPowerCapture] = {}
        # device_index -> index of the band currently being scanned
        self._cycle_idx: dict[int, int] = {}
        # device_index -> active cycle Timer
        self._timers: dict[int, threading.Timer] = {}
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
        """Start a list of bands grouped by device."""
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
        """Cancel any pending cycle timer, stop current capture, start cycle."""
        timer = self._timers.pop(device_index, None)
        if timer:
            timer.cancel()

        cap = self._captures.get(device_index)
        if cap:
            cap.stop()

        bands = list(self._active.get(device_index, {}).values())
        if not bands:
            self._captures.pop(device_index, None)
            log.info("Device %d has no active bands — capture stopped", device_index)
            return

        self._cycle_idx[device_index] = 0
        # _restart_device is called holding self._lock; start first band directly
        self._run_band_locked(device_index)

    def _run_band(self, device_index: int) -> None:
        """Start the current band in the cycle (called without self._lock)."""
        with self._lock:
            bands = list(self._active.get(device_index, {}).values())
            if not bands:
                return
            idx = self._cycle_idx.get(device_index, 0) % len(bands)
            band = bands[idx]
            self._cycle_idx[device_index] = (idx + 1) % len(bands)

        # Stop previous capture
        cap = self._captures.get(device_index)
        if cap:
            cap.stop()

        log.info("Device %d → scanning [%s] %s", device_index, band["id"], band["name"])
        cap = RTLPowerCapture()
        try:
            cap.start([band], device_index)
        except RuntimeError as exc:
            log.warning("Failed to start [%s]: %s", band["id"], exc)
        self._captures[device_index] = cap

        # Schedule switch to next band after this band's interval
        timer = threading.Timer(
            band["interval_s"], self._run_band, args=[device_index]
        )
        timer.daemon = True
        timer.start()
        with self._lock:
            self._timers[device_index] = timer

    def _run_band_locked(self, device_index: int) -> None:
        """Start first band — called while self._lock is already held."""
        bands = list(self._active.get(device_index, {}).values())
        if not bands:
            return
        idx = self._cycle_idx.get(device_index, 0) % len(bands)
        band = bands[idx]
        self._cycle_idx[device_index] = (idx + 1) % len(bands)

        log.info("Device %d → scanning [%s] %s", device_index, band["id"], band["name"])
        cap = RTLPowerCapture()
        try:
            cap.start([band], device_index)
        except RuntimeError as exc:
            log.warning("Failed to start [%s]: %s", band["id"], exc)
        self._captures[device_index] = cap

        timer = threading.Timer(
            band["interval_s"], self._run_band, args=[device_index]
        )
        timer.daemon = True
        timer.start()
        self._timers[device_index] = timer


from app.config import DEMO_MODE

if DEMO_MODE:
    from app.demo.player import DemoBandPlayer
    band_manager = DemoBandPlayer()
else:
    band_manager = BandCaptureManager()
