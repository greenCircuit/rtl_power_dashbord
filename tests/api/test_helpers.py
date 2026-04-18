"""Regression tests for app/api/routes/_helpers.py.

Bug caught: _get_devices() called _list_rtl_devices() (which runs rtl_test
with a 3-second timeout) even in demo mode where no hardware exists.  In demo
mode the probe must be skipped entirely.
"""

from unittest.mock import patch, MagicMock
import subprocess


def _reset_device_cache(monkeypatch):
    import app.api.routes._helpers as h
    monkeypatch.setattr(h, "_device_cache", None)


# ── demo mode: rtl_test must never be called ──────────────────────────────────

def test_get_devices_skips_subprocess_in_demo_mode(monkeypatch):
    """_get_devices() must not spawn rtl_test when DEMO_MODE=True."""
    _reset_device_cache(monkeypatch)
    monkeypatch.setattr("app.api.routes._helpers.__import__", __import__, raising=False)

    with patch("app.api.routes._helpers.DEMO_MODE", True, create=True), \
         patch("app.config.DEMO_MODE", True), \
         patch("subprocess.run") as mock_run:

        # Re-import to pick up the patched DEMO_MODE inside the function
        import importlib
        import app.api.routes._helpers as h
        monkeypatch.setattr(h, "_device_cache", None)

        # Patch DEMO_MODE at the point where _get_devices reads it
        with patch.object(h, "_device_cache", None):
            original_get_devices = h._get_devices

            def patched_get_devices():
                # Inline the logic with DEMO_MODE forced True
                if h._device_cache is None:
                    h._device_cache = []  # skip _list_rtl_devices
                    if not h._device_cache:
                        h._device_cache = [{"index": 0, "name": "Device 0"}]
                return h._device_cache

            # The real test: call the actual function with DEMO_MODE patched
            monkeypatch.setattr(h, "_device_cache", None)
            with patch("app.config.DEMO_MODE", True):
                result = h._get_devices()

        mock_run.assert_not_called()
        assert result == [{"index": 0, "name": "Device 0"}]


def test_get_devices_calls_rtl_test_when_not_demo(monkeypatch):
    """_get_devices() must probe rtl_test when DEMO_MODE=False."""
    import app.api.routes._helpers as h
    monkeypatch.setattr(h, "_device_cache", None)

    mock_result = MagicMock()
    mock_result.stderr = ""
    mock_result.stdout = ""

    with patch("app.config.DEMO_MODE", False), \
         patch("subprocess.run", return_value=mock_result) as mock_run:
        monkeypatch.setattr(h, "_device_cache", None)
        h._get_devices()

    mock_run.assert_called_once()


def test_get_devices_returns_fallback_when_rtl_test_finds_nothing(monkeypatch):
    """When rtl_test produces no device lines the fallback Device 0 is returned."""
    import app.api.routes._helpers as h
    monkeypatch.setattr(h, "_device_cache", None)

    mock_result = MagicMock()
    mock_result.stderr = ""
    mock_result.stdout = ""

    with patch("app.config.DEMO_MODE", False), \
         patch("subprocess.run", return_value=mock_result):
        monkeypatch.setattr(h, "_device_cache", None)
        devices = h._get_devices()

    assert devices == [{"index": 0, "name": "Device 0"}]


def test_get_devices_cached_after_first_call(monkeypatch):
    """Second call must reuse the cache and not call subprocess.run again."""
    import app.api.routes._helpers as h
    monkeypatch.setattr(h, "_device_cache", None)

    mock_result = MagicMock()
    mock_result.stderr = ""
    mock_result.stdout = ""

    with patch("app.config.DEMO_MODE", False), \
         patch("subprocess.run", return_value=mock_result) as mock_run:
        monkeypatch.setattr(h, "_device_cache", None)
        h._get_devices()
        h._get_devices()

    assert mock_run.call_count == 1
