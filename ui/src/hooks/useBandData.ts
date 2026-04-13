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
  Filters,
} from '../api'

interface FetchResult<T> {
  data: T | null
  error: boolean
}

// ── Generic base hook ─────────────────────────────────────────────────────────

function useBandFetch<T>(
  fetcher: (id: string, qs: string) => Promise<T>,
  bandId: string | null,
  filters: Filters,
  extra: Record<string, string | number>,
  deps: unknown[],
): FetchResult<T> {
  const [data,  setData]  = useState<T | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!bandId) { setData(null); setError(false); return }
    let cancelled = false
    fetcher(bandId, filtersToQS(filters, extra))
      .then(d  => { if (!cancelled) { setData(d); setError(false) } })
      .catch(() => { if (!cancelled) { setData(null); setError(true) } })
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bandId, ...deps])

  return { data, error }
}

// ── Public hooks ──────────────────────────────────────────────────────────────

export function useHeatmap(): FetchResult<HeatmapData> {
  const bandId  = useStore(s => s.bandId)
  const filters = useStore(s => s.filters)
  const refresh = useStore(s => s.refreshTick)
  return useBandFetch(api.fetchHeatmap, bandId, filters, {}, [filters, refresh])
}

export function useSpectrum(): FetchResult<SpectrumData> {
  const bandId  = useStore(s => s.bandId)
  const filters = useStore(s => s.filters)
  const refresh = useStore(s => s.refreshTick)
  return useBandFetch(api.fetchSpectrum, bandId, filters, {}, [filters, refresh])
}

export function useActivity(): FetchResult<ActivityData> {
  const bandId    = useStore(s => s.bandId)
  const filters   = useStore(s => s.filters)
  const threshold = useStore(s => s.threshold)
  const refresh   = useStore(s => s.refreshTick)
  return useBandFetch(api.fetchActivity, bandId, filters, { threshold }, [filters, threshold, refresh])
}

export function useTodActivity(): FetchResult<TodData> {
  const bandId    = useStore(s => s.bandId)
  const filters   = useStore(s => s.filters)
  const threshold = useStore(s => s.threshold)
  const analysis  = useStore(s => s.analysisRefreshTick)
  return useBandFetch(api.fetchTodActivity, bandId, filters, { threshold }, [filters, threshold, analysis])
}

export function useDurations(): FetchResult<DurationData> {
  const bandId    = useStore(s => s.bandId)
  const filters   = useStore(s => s.filters)
  const threshold = useStore(s => s.threshold)
  const analysis  = useStore(s => s.analysisRefreshTick)
  return useBandFetch(api.fetchDurations, bandId, filters, { threshold }, [filters, threshold, analysis])
}

export function usePowerHistogram(): FetchResult<PowerHistogramData> {
  const bandId  = useStore(s => s.bandId)
  const filters = useStore(s => s.filters)
  const refresh = useStore(s => s.refreshTick)
  return useBandFetch(api.fetchPowerHistogram, bandId, filters, {}, [filters, refresh])
}

export function useTopChannels(): FetchResult<TopChannelsData> {
  const bandId    = useStore(s => s.bandId)
  const filters   = useStore(s => s.filters)
  const threshold = useStore(s => s.threshold)
  const refresh   = useStore(s => s.refreshTick)
  return useBandFetch(api.fetchTopChannels, bandId, filters, { threshold }, [filters, threshold, refresh])
}

export function useActivityTrend(granularity: string): FetchResult<ActivityTrendData> {
  const bandId    = useStore(s => s.bandId)
  const filters   = useStore(s => s.filters)
  const threshold = useStore(s => s.threshold)
  const analysis  = useStore(s => s.analysisRefreshTick)
  return useBandFetch(
    api.fetchActivityTrend, bandId, filters,
    { threshold, granularity },
    [filters, threshold, granularity, analysis],
  )
}

export function useTimeseries(): FetchResult<TimeseriesData> {
  const bandId  = useStore(s => s.bandId)
  const filters = useStore(s => s.filters)
  const freq    = useStore(s => s.selectedFreq)
  const [data,  setData]  = useState<TimeseriesData | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!bandId || freq == null) { setData(null); setError(false); return }
    let cancelled = false
    api.fetchTimeseries(bandId, filtersToQS(filters, { freq_mhz: freq }))
      .then(d  => { if (!cancelled) { setData(d); setError(false) } })
      .catch(() => { if (!cancelled) { setData(null); setError(true) } })
    return () => { cancelled = true }
  }, [bandId, filters, freq])

  return { data, error }
}
