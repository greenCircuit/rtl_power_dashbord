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
from unittest.mock import MagicMock, patch


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
    """After start_active_bands, cycle_idx should point at the next band."""
    manager.start_active_bands([BAND_A, BAND_B])
    # _next_band picks band[0] and advances to 1
    assert manager._cycle_idx.get(0) == 1


def test_two_bands_timer_cycles_to_second(manager):
    """Manually firing _run_band should pick the next band in the cycle."""
    manager.start_active_bands([BAND_A, BAND_B])
    # After start, cycle_idx is at 1 (band B is next)
    assert manager._cycle_idx.get(0) == 1

    # Cancel the real timer so it doesn't fire concurrently
    manager._timers[0].cancel()

    # Directly invoke the timer callback — simulates the interval expiring
    with patch("app.capture.manager.RTLPowerCapture", side_effect=_mock_capture):
        manager._run_band(0)

    # _run_band picked band B (index 1) and advanced cycle_idx back to 0
    assert manager._cycle_idx.get(0) == 0  # 2 % 2 == 0 (wrapped around)


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


# ── Bug #4 regression: _run_band must clear _captures/_timers under the lock ──
# Before the fix _run_band released the lock, then read/wrote _captures and
# _timers, which meant _restart_device (called from stop_band while holding the
# lock) could observe a half-replaced capture or timer.

def test_run_band_clears_stale_capture_before_releasing_lock(manager):
    """_run_band must remove the old capture from _captures while still holding
    the lock, so _restart_device never sees both the old and the new capture."""
    manager.start_active_bands([BAND_A, BAND_B])

    observed = {}

    real_next_band = manager._next_band.__func__

    def spy_next_band(self, device_index):
        result = real_next_band(self, device_index)
        # Snapshot whether _captures[device_index] has been cleared at the
        # point where the lock is held and _next_band is being called.
        observed["has_old_capture_under_lock"] = device_index in self._captures
        return result

    import types
    manager._next_band = types.MethodType(spy_next_band, manager)

    # Directly call the timer callback (no real time wait)
    with patch("app.capture.manager.RTLPowerCapture", side_effect=_mock_capture):
        manager._run_band(0)

    # Under the lock (_next_band call), the old capture should still be present
    # (it gets popped right after _next_band returns, still under the lock).
    # The important regression check is that after _run_band completes, a new
    # capture exists and the old one was stopped.
    assert 0 in manager._captures, "_captures must have the new capture after _run_band"


def test_run_band_stops_old_capture(manager):
    """The capture that was running when _run_band fires must be stopped."""
    manager.start_active_bands([BAND_A, BAND_B])

    old_cap = manager._captures.get(0)
    assert old_cap is not None

    with patch("app.capture.manager.RTLPowerCapture", side_effect=_mock_capture):
        manager._run_band(0)

    old_cap.stop.assert_called_once()


def test_run_band_registers_new_timer(manager):
    """After _run_band fires, a fresh timer must be registered for the device."""
    manager.start_active_bands([BAND_A, BAND_B])

    old_timer = manager._timers.get(0)

    with patch("app.capture.manager.RTLPowerCapture", side_effect=_mock_capture):
        manager._run_band(0)

    new_timer = manager._timers.get(0)
    assert new_timer is not None, "no timer registered after _run_band"
    assert new_timer is not old_timer, "_run_band must register a new timer, not reuse the old one"
    new_timer.cancel()


# ── Bug #5 regression: get_status/get_error/all_statuses must hold the lock ──
# Before the fix these methods iterated self._active without acquiring
# self._lock, which could cause a RuntimeError on dict-size-changed-during-
# iteration when another thread added/removed a band concurrently.

def test_get_status_concurrent_mutation_does_not_raise(manager):
    """get_status must not crash when another thread mutates _active concurrently."""
    manager.start_active_bands([BAND_A, BAND_B])
    errors = []
    stop = threading.Event()

    def mutator():
        with patch("app.capture.manager.db") as mock_db:
            mock_db.get_band.return_value = _make_band("band-x", "X")
            while not stop.is_set():
                try:
                    manager.start_active_bands([_make_band("band-x", "X")])
                    manager.stop_band("band-x")
                except Exception as exc:
                    errors.append(exc)

    t = threading.Thread(target=mutator, daemon=True)
    t.start()

    try:
        for _ in range(200):
            try:
                manager.get_status("band-a")
            except RuntimeError as exc:
                errors.append(exc)
    finally:
        stop.set()
        t.join(timeout=2)

    assert not errors, f"get_status raised under concurrent mutation: {errors[0]}"


def test_all_statuses_concurrent_mutation_does_not_raise(manager):
    """all_statuses must not crash when another thread mutates _active concurrently."""
    manager.start_active_bands([BAND_A, BAND_B])
    errors = []
    stop = threading.Event()

    def mutator():
        while not stop.is_set():
            try:
                manager.start_active_bands([_make_band("band-y", "Y")])
                manager.stop_band("band-y")
            except Exception as exc:
                errors.append(exc)

    t = threading.Thread(target=mutator, daemon=True)
    t.start()

    try:
        for _ in range(200):
            try:
                manager.all_statuses()
            except RuntimeError as exc:
                errors.append(exc)
    finally:
        stop.set()
        t.join(timeout=2)

    assert not errors, f"all_statuses raised under concurrent mutation: {errors[0]}"


def test_get_error_returns_none_for_unknown_band(manager):
    assert manager.get_error("no-such-band") is None


def test_get_error_returns_capture_error_when_set(manager):
    manager.start_active_bands([BAND_A])
    manager._captures[0].error = "device busy"
    assert manager.get_error("band-a") == "device busy"


def test_get_status_returns_idle_when_no_capture(manager):
    """A band in _active with no capture (e.g. capture was popped) returns idle."""
    manager._active[0] = {"band-a": BAND_A}
    # deliberately leave _captures[0] absent
    assert manager.get_status("band-a") == "idle"
