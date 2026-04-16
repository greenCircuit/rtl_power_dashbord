"""
Database package — re-exports every public symbol so that all existing
``from app.data.db import X`` and ``import app.data.db as db`` call-sites
continue to work without modification.
"""

from ._engine import (          # noqa: F401
    Base,
    Band,
    BandMeasurement,
    get_engine,
    init_db,
)

from .bands import (            # noqa: F401
    list_bands,
    get_band,
    create_band,
    update_band,
    delete_band,
    seed_bands_from_yaml,
    _seed_one_band,
)

from .measurements import (     # noqa: F401
    insert_band_measurements,
    fetch_band_measurements,
    fetch_band_stats,
    fetch_band_activity,
    fetch_band_closest_freq,
    fetch_band_timeseries,
    fetch_band_latest_activity,
    fetch_band_alltime_peak,
    fetch_band_power_histogram,
    fetch_band_top_channels,
    fetch_band_signal_raw,
)

from .analysis import (         # noqa: F401
    GRANULARITY_SECONDS,
    fetch_band_tod_activity,
    fetch_band_activity_timeline,
    fetch_band_activity_trend,
    fetch_band_power_envelope,
)

from .maintenance import (      # noqa: F401
    cleanup_old_data,
    fetch_db_status,
)
