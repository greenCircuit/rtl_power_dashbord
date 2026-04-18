import { useState, useEffect } from 'react'
import { useStore } from '../store'
import { api, filtersToQS } from '../api'
import type {
  HeatmapData,
  SpectrumData,
  ActivityData,
  TodData,
  DurationData,
  TimeseriesData,
  PowerHistogramData,
  TopChannelsData,
  ActivityTrendData,
  NoiseFloorData,
  Filters,
} from '../api'

interface FetchResult<T> {
  data: T | null
  error: boolean
}

// ── Generic base hook ─────────────────────────────────────────────────────────

// resetDeps  — structural changes (band, filters, threshold) that require the
//              chart to be destroyed and recreated from scratch.  data is set to
//              null immediately so useChart tears down the old instance and calls
//              create() with fresh closures on the next render.
// tickDeps   — periodic refresh ticks.  data is NOT cleared so the existing
//              chart stays visible and useChart calls update() in place — no flicker.
function useBandFetch<T>(
  fetcher: (id: string, qs: string) => Promise<T>,
  bandId: string | null,
  filters: Filters,
  extra: Record<string, string | number>,
  resetDeps: unknown[],
  tickDeps: unknown[],
): FetchResult<T> {
  const [data,  setData]  = useState<T | null>(null)
  const [error, setError] = useState(false)

  // Hard reset: clear data so the chart recreates from scratch.
  useEffect(() => {
    setData(null)
    setError(false)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bandId, ...resetDeps])

  // Fetch on every dep change; on tick-only changes data stays non-null so the
  // chart updates in place without flickering.
  useEffect(() => {
    if (!bandId) return
    let cancelled = false
    fetcher(bandId, filtersToQS(filters, extra))
      .then(d  => { if (!cancelled) { setData(d); setError(false) } })
      .catch(() => { if (!cancelled) { setData(null); setError(true) } })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bandId, ...resetDeps, ...tickDeps])

  return { data, error }
}

// ── Public hooks ──────────────────────────────────────────────────────────────

// In live mode (timeRange === '1m') filter changes are treated as ticks, not
// resets, so charts update in place without clearing to null first (no flicker).
function useIsLive() { return useStore(s => s.timeRange) === '1m' }

export function useHeatmap(): FetchResult<HeatmapData> {
  const bandId  = useStore(s => s.bandId)
  const filters = useStore(s => s.filters)
  const refresh = useStore(s => s.refreshTick)
  const live    = useIsLive()
  return useBandFetch(api.fetchHeatmap, bandId, filters, {},
    live ? [] : [filters], live ? [filters, refresh] : [refresh])
}

export function useSpectrum(): FetchResult<SpectrumData> {
  const bandId  = useStore(s => s.bandId)
  const filters = useStore(s => s.filters)
  const refresh = useStore(s => s.refreshTick)
  const live    = useIsLive()
  return useBandFetch(api.fetchSpectrum, bandId, filters, {},
    live ? [] : [filters], live ? [filters, refresh] : [refresh])
}

export function useActivity(): FetchResult<ActivityData> {
  const bandId    = useStore(s => s.bandId)
  const filters   = useStore(s => s.filters)
  const threshold = useStore(s => s.threshold)
  const refresh   = useStore(s => s.refreshTick)
  const live      = useIsLive()
  return useBandFetch(api.fetchActivity, bandId, filters, { threshold },
    live ? [threshold] : [filters, threshold], live ? [filters, refresh] : [refresh])
}

export function useTodActivity(): FetchResult<TodData> {
  const bandId    = useStore(s => s.bandId)
  const filters   = useStore(s => s.filters)
  const threshold = useStore(s => s.threshold)
  const analysis  = useStore(s => s.analysisRefreshTick)
  const live      = useIsLive()
  return useBandFetch(api.fetchTodActivity, bandId, filters, { threshold },
    live ? [threshold] : [filters, threshold], live ? [filters, analysis] : [analysis])
}

export function useDurations(): FetchResult<DurationData> {
  const bandId    = useStore(s => s.bandId)
  const filters   = useStore(s => s.filters)
  const threshold = useStore(s => s.threshold)
  const analysis  = useStore(s => s.analysisRefreshTick)
  const live      = useIsLive()
  return useBandFetch(api.fetchDurations, bandId, filters, { threshold },
    live ? [threshold] : [filters, threshold], live ? [filters, analysis] : [analysis])
}

export function usePowerHistogram(): FetchResult<PowerHistogramData> {
  const bandId  = useStore(s => s.bandId)
  const filters = useStore(s => s.filters)
  const refresh = useStore(s => s.refreshTick)
  const live    = useIsLive()
  return useBandFetch(api.fetchPowerHistogram, bandId, filters, {},
    live ? [] : [filters], live ? [filters, refresh] : [refresh])
}

export function useTopChannels(): FetchResult<TopChannelsData> {
  const bandId    = useStore(s => s.bandId)
  const filters   = useStore(s => s.filters)
  const threshold = useStore(s => s.threshold)
  const refresh   = useStore(s => s.refreshTick)
  const live      = useIsLive()
  return useBandFetch(api.fetchTopChannels, bandId, filters, { threshold },
    live ? [threshold] : [filters, threshold], live ? [filters, refresh] : [refresh])
}

export function useActivityTrend(granularity: string): FetchResult<ActivityTrendData> {
  const bandId    = useStore(s => s.bandId)
  const filters   = useStore(s => s.filters)
  const threshold = useStore(s => s.threshold)
  const analysis  = useStore(s => s.analysisRefreshTick)
  const live      = useIsLive()
  return useBandFetch(
    api.fetchActivityTrend, bandId, filters,
    { threshold, granularity },
    live ? [threshold, granularity] : [filters, threshold, granularity],
    live ? [filters, analysis] : [analysis],
  )
}

export function useNoiseFloor(granularity: string): FetchResult<NoiseFloorData> {
  const bandId   = useStore(s => s.bandId)
  const filters  = useStore(s => s.filters)
  const analysis = useStore(s => s.analysisRefreshTick)
  const live     = useIsLive()
  return useBandFetch(
    api.fetchNoiseFloor, bandId, filters,
    { granularity },
    live ? [granularity] : [filters, granularity],
    live ? [filters, analysis] : [analysis],
  )
}

export function useTimeseries(): FetchResult<TimeseriesData> {
  const bandId  = useStore(s => s.bandId)
  const filters = useStore(s => s.filters)
  const freq    = useStore(s => s.selectedFreq)
  const live    = useIsLive()
  const [data,  setData]  = useState<TimeseriesData | null>(null)
  const [error, setError] = useState(false)

  // Hard reset when band or selected frequency changes.
  useEffect(() => {
    setData(null); setError(false)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bandId, freq, ...(live ? [] : [filters])])

  useEffect(() => {
    if (!bandId || freq == null) return
    let cancelled = false
    api.fetchTimeseries(bandId, filtersToQS(filters, { freq_mhz: freq }))
      .then(d  => { if (!cancelled) { setData(d); setError(false) } })
      .catch(() => { if (!cancelled) { setData(null); setError(true) } })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bandId, filters, freq])

  return { data, error }
}
