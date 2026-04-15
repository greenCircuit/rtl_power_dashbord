"""Band CRUD and YAML seed functions."""

import logging
from pathlib import Path

import yaml

from ._engine import Band, BandMeasurement, _session, BANDS_CONFIG

log = logging.getLogger(__name__)


def _to_dict(b: Band) -> dict:
    return {
        "id":           b.id,
        "name":         b.name,
        "freq_start":   b.freq_start,
        "freq_end":     b.freq_end,
        "freq_step":    b.freq_step,
        "interval_s":   b.interval_s,
        "min_power":    b.min_power,
        "device_index": b.device_index,
        "is_active":    bool(b.is_active),
    }


def list_bands() -> list[dict]:
    with _session() as sess:
        return [_to_dict(b) for b in sess.query(Band).order_by(Band.name).all()]


def get_band(band_id: str) -> dict | None:
    with _session() as sess:
        b = sess.get(Band, band_id)
        return _to_dict(b) if b else None


def create_band(band_id, name, freq_start, freq_end, freq_step,
                interval_s, min_power, device_index, is_active=False) -> None:
    with _session() as sess:
        if sess.get(Band, band_id):
            raise ValueError(f"Band {band_id!r} already exists")
        sess.add(Band(
            id=band_id, name=name,
            freq_start=str(freq_start), freq_end=str(freq_end), freq_step=str(freq_step),
            interval_s=int(interval_s), min_power=float(min_power),
            device_index=int(device_index), is_active=bool(is_active),
        ))
        sess.commit()


def update_band(band_id, name, freq_start, freq_end, freq_step,
                interval_s, min_power, device_index, is_active=False) -> None:
    with _session() as sess:
        b = sess.get(Band, band_id)
        if not b:
            raise ValueError(f"Band {band_id!r} not found")
        b.name         = name
        b.freq_start   = str(freq_start)
        b.freq_end     = str(freq_end)
        b.freq_step    = str(freq_step)
        b.interval_s   = int(interval_s)
        b.min_power    = float(min_power)
        b.device_index = int(device_index)
        b.is_active    = bool(is_active)
        sess.commit()


def delete_band(band_id: str) -> None:
    with _session() as sess:
        sess.query(BandMeasurement).filter(BandMeasurement.band_id == band_id).delete()
        b = sess.get(Band, band_id)
        if b:
            sess.delete(b)
        sess.commit()


def seed_bands_from_yaml(config_path: Path = BANDS_CONFIG) -> None:
    if not config_path.exists():
        log.warning("Bands config not found: %s", config_path)
        return
    with open(config_path) as fh:
        cfg = yaml.safe_load(fh)
    bands = cfg.get("bands", []) if cfg else []
    _REQUIRED = ("id", "name", "freq_start", "freq_end", "freq_step")
    with _session() as sess:
        for b in bands:
            missing = [k for k in _REQUIRED if k not in b]
            if missing:
                log.warning("Skipping malformed band entry (missing keys: %s): %r", missing, b)
                continue
            try:
                if sess.get(Band, b["id"]) is None:
                    sess.add(Band(
                        id=str(b["id"]),
                        name=str(b["name"]),
                        freq_start=str(b["freq_start"]),
                        freq_end=str(b["freq_end"]),
                        freq_step=str(b["freq_step"]),
                        interval_s=int(b.get("interval_s", 10)),
                        min_power=float(b.get("min_power", 2.0)),
                        device_index=int(b.get("device_index", 0)),
                        is_active=bool(b.get("is_active", False)),
                    ))
                    log.info("Seeded band: %s (%s)", b["id"], b["name"])
            except Exception as exc:
                log.warning("Skipping band entry %r due to error: %s", b.get("id"), exc)
        sess.commit()


def _seed_one_band(_conn, b: dict) -> bool:
    """Insert one band from a seed dict if it doesn't already exist.

    *_conn* is accepted for API compatibility with legacy callers but is ignored
    — the function uses the module-level SQLAlchemy session.
    Returns True if the band was inserted, False if it already existed.
    """
    if get_band(str(b["id"])) is not None:
        return False
    create_band(
        band_id=str(b["id"]),
        name=str(b["name"]),
        freq_start=str(b["freq_start"]),
        freq_end=str(b["freq_end"]),
        freq_step=str(b["freq_step"]),
        interval_s=int(b.get("interval_s", 10)),
        min_power=float(b.get("min_power", 2.0)),
        device_index=int(b.get("device_index", 0)),
        is_active=bool(b.get("is_active", False)),
    )
    return True
