"""Tests for BandCaptureManager.

Key regression covered here: any public method that acquires self._lock and
then (directly or via _restart_device) calls into _run_band_locked vs _run_band
must NOT cause a self-deadlock.  Python's threading.Lock is non-reentrant, so
acquiring it twice in the same thread blocks forever.

The bug: _restart_device() was called while self._lock was held, but it called
_run_band() which did `with self._lock:` again → permanent hang on startup.
"""

import threading
import pytest
from unittest.mock import MagicMock, patch, call


# ── shared band dicts ─────────────────────────────────────────────────────────

def _make_band(band_id, name, device=0, interval=9999):
    """Return a minimal band dict.  interval=9999 so timers don't fire during tests."""
    return {
        "id": band_id, "name": name,
        "device_index": device,
        "freq_start": "144M", "freq_end": "146M", "freq_step": "25k",
        "interval_s": interval,
        "min_power": -20,
    }


BAND_A = _make_band("band-a", "Band A")
BAND_B = _make_band("band-b", "Band B")
BAND_C = _make_band("band-c", "Band C", device=1)   # different device


# ── fixtures ──────────────────────────────────────────────────────────────────

def _mock_capture():
    cap = MagicMock()
    cap.status = "running"
    cap.error = None
    return cap


@pytest.fixture
def manager():
    """Fresh BandCaptureManager with RTLPowerCapture patched to a no-op mock."""
    from app.capture.manager import BandCaptureManager

    with patch("app.capture.manager.RTLPowerCapture", side_effect=_mock_capture):
        mgr = BandCaptureManager()
        yield mgr

    # Clean up any leftover timers so threads don't outlive the test
    for timer in list(mgr._timers.values()):
        timer.cancel()


def _run_with_timeout(fn, timeout=2.0) -> bool:
    """Run fn() in a daemon thread; return True if it completes before timeout."""
    completed = threading.Event()

    def wrapper():
        fn()
        completed.set()

    t = threading.Thread(target=wrapper, daemon=True)
    t.start()
    return completed.wait(timeout=timeout)


# ── deadlock regression tests ─────────────────────────────────────────────────
# Each public method acquires self._lock and then calls _restart_device(), which
# must use _run_band_locked() (lock already held) and NOT _run_band() (which
# would try to re-acquire the same non-reentrant lock and hang forever).

def test_start_active_bands_single_band_no_deadlock(manager):
    assert _run_with_timeout(lambda: manager.start_active_bands([BAND_A])), (
        "start_active_bands deadlocked — _restart_device likely called _run_band "
        "instead of _run_band_locked while holding self._lock"
    )


def test_start_active_bands_two_bands_same_device_no_deadlock(manager):
    assert _run_with_timeout(lambda: manager.start_active_bands([BAND_A, BAND_B])), (
        "start_active_bands deadlocked with two bands on the same device"
    )


def test_start_active_bands_two_devices_no_deadlock(manager):
    assert _run_with_timeout(lambda: manager.start_active_bands([BAND_A, BAND_C])), (
        "start_active_bands deadlocked with bands on separate devices"
    )


def test_start_band_no_deadlock(manager):
    with patch("app.capture.manager.db") as mock_db:
        mock_db.get_band.return_value = BAND_A
        assert _run_with_timeout(lambda: manager.start_band("band-a")), (
            "start_band deadlocked"
        )


def test_stop_band_no_deadlock(manager):
    manager.start_active_bands([BAND_A])
    assert _run_with_timeout(lambda: manager.stop_band("band-a")), (
        "stop_band deadlocked"
    )


def test_stop_band_then_start_again_no_deadlock(manager):
    """Cycle: start → stop → start must not deadlock."""
    manager.start_active_bands([BAND_A])
    manager.stop_band("band-a")
    assert _run_with_timeout(lambda: manager.start_active_bands([BAND_A])), (
        "Second start_active_bands after stop deadlocked"
    )


# ── functional behaviour ──────────────────────────────────────────────────────

def test_start_active_bands_creates_capture(manager):
    manager.start_active_bands([BAND_A])
    assert 0 in manager._captures, "No capture created for device 0"


def test_start_active_bands_status_running(manager):
    manager.start_active_bands([BAND_A])
    assert manager.get_status("band-a") == "running"


def test_stop_band_status_becomes_idle(manager):
    manager.start_active_bands([BAND_A])
    manager.stop_band("band-a")
    assert manager.get_status("band-a") == "idle"


def test_stop_last_band_removes_capture(manager):
    manager.start_active_bands([BAND_A])
    manager.stop_band("band-a")
    assert 0 not in manager._captures


def test_unknown_band_status_is_idle(manager):
    assert manager.get_status("does-not-exist") == "idle"


def test_all_statuses_reflects_active_bands(manager):
    manager.start_active_bands([BAND_A, BAND_B])
    statuses = manager.all_statuses()
    assert set(statuses.keys()) == {"band-a", "band-b"}
    assert all(s == "running" for s in statuses.values())


def test_start_band_already_active_raises(manager):
    with patch("app.capture.manager.db") as mock_db:
        mock_db.get_band.return_value = BAND_A
        manager.start_band("band-a")
        with pytest.raises(RuntimeError, match="already capturing"):
            manager.start_band("band-a")


# ── band cycling ──────────────────────────────────────────────────────────────

def test_two_bands_cycle_idx_advances(manager):
    """After the first band starts, cycle_idx should point at the next band."""
    manager.start_active_bands([BAND_A, BAND_B])
    # _run_band_locked increments cycle_idx after picking band[0]
    assert manager._cycle_idx.get(0) == 1


def test_two_bands_timer_cycles_to_second(manager):
    """Manually fire the timer callback and verify the second band starts."""
    short_a = {**BAND_A, "interval_s": 0.05}
    short_b = {**BAND_B, "interval_s": 0.05}

    with patch("app.capture.manager.RTLPowerCapture", side_effect=_mock_capture):
        from app.capture.manager import BandCaptureManager
        mgr = BandCaptureManager()

    manager.start_active_bands([short_a, short_b])

    # Manually invoke the timer callback (simulates the interval expiring)
    timer = mgr._timers.get(0)
    if timer:
        timer.cancel()

    # Direct call to _run_band (the timer target) without waiting for real time
    with patch("app.capture.manager.RTLPowerCapture", side_effect=_mock_capture):
        manager._run_band(0)

    # After cycling, the second call should have picked band index 1
    assert manager._cycle_idx.get(0) == 0  # wrapped back around: 2 % 2 == 0


def test_two_bands_on_separate_devices_independent(manager):
    """Bands on different devices must each get their own capture."""
    manager.start_active_bands([BAND_A, BAND_C])
    assert 0 in manager._captures, "No capture for device 0"
    assert 1 in manager._captures, "No capture for device 1"


def test_stop_one_device_leaves_other_running(manager):
    manager.start_active_bands([BAND_A, BAND_C])
    manager.stop_band("band-a")
    assert manager.get_status("band-c") == "running"
    assert manager.get_status("band-a") == "idle"
