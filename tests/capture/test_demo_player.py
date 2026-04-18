"""Regression tests for DemoBandPlayer.

Bug caught: all_statuses() acquired self._lock then called self.get_status()
which also tried to acquire self._lock — Python's Lock is non-reentrant so
it deadlocked forever.
"""

import threading
from unittest.mock import patch


def _make_band(band_id, name="Test Band", interval=9999):
    return {
        "id":           band_id,
        "name":         name,
        "freq_start":   "144M",
        "freq_end":     "146M",
        "freq_step":    "25k",
        "interval_s":   interval,
        "min_power":    -100.0,
        "device_index": 0,
        "is_active":    True,
    }


def _run_with_timeout(fn, timeout=2.0) -> bool:
    """Run fn() in a daemon thread; return True if it completes before timeout."""
    done = threading.Event()

    def wrapper():
        fn()
        done.set()

    threading.Thread(target=wrapper, daemon=True).start()
    return done.wait(timeout=timeout)


# Patch _replay so no real DB writes happen during these tests.
def _noop_replay(band, interval_s, stop_event):
    stop_event.wait()


def _make_player():
    from app.demo.player import DemoBandPlayer
    return DemoBandPlayer()


# ── deadlock regression ───────────────────────────────────────────────────────

def test_all_statuses_does_not_deadlock():
    """all_statuses() must not deadlock by re-acquiring self._lock via get_status()."""
    with patch("app.demo.player._replay", side_effect=_noop_replay):
        player = _make_player()
        player.start_active_bands([_make_band("b1"), _make_band("b2")])
        assert _run_with_timeout(player.all_statuses), (
            "all_statuses deadlocked — it likely called get_status() while "
            "already holding self._lock (Lock is non-reentrant)"
        )
        player.stop_band("b1")
        player.stop_band("b2")


def test_all_statuses_returns_running_for_active_bands():
    # start_active_bands always overlays DEMO_BANDS, so our bands are a subset
    with patch("app.demo.player._replay", side_effect=_noop_replay):
        player = _make_player()
        player.start_active_bands([_make_band("b1"), _make_band("b2")])
        statuses = player.all_statuses()
        assert {"b1", "b2"}.issubset(statuses.keys())
        player.stop_band("b1")
        player.stop_band("b2")


def test_all_statuses_empty_when_no_bands():
    player = _make_player()
    assert player.all_statuses() == {}


def test_get_status_does_not_deadlock():
    """get_status() must also complete without deadlocking."""
    with patch("app.demo.player._replay", side_effect=_noop_replay):
        player = _make_player()
        player.start_active_bands([_make_band("b1")])
        assert _run_with_timeout(lambda: player.get_status("b1")), (
            "get_status deadlocked"
        )
        player.stop_band("b1")


def test_stop_band_status_becomes_stopped():
    with patch("app.demo.player._replay", side_effect=_noop_replay):
        player = _make_player()
        player.start_active_bands([_make_band("b1")])
        player.stop_band("b1")
        assert player.get_status("b1") == "stopped"


def test_get_error_always_none():
    player = _make_player()
    assert player.get_error("any-band") is None
