import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useStore } from '../store'
import { useHeatmap, useSpectrum, useActivity } from '../hooks/useBandData'
import type { HeatmapData, SpectrumData, ActivityData } from '../api'

// Mock the entire api module so no real HTTP calls are made
vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      fetchHeatmap:  vi.fn(),
      fetchSpectrum: vi.fn(),
      fetchActivity: vi.fn(),
    },
  }
})

import { api } from '../api'

const INITIAL = useStore.getState()

beforeEach(() => {
  useStore.setState(INITIAL, true)
  vi.clearAllMocks()
})

const mockHeatmap: HeatmapData = {
  x: ['2024-01-01 00:00:00'],
  y: [144.0],
  z: [[0]],
  freq_min: 144,
  freq_max: 146,
  time_min: '2024-01-01 00:00:00',
  time_max: '2024-01-01 01:00:00',
}

const mockSpectrum: SpectrumData = {
  frequency_mhz: [144.0],
  mean_db: [-50],
  peak_db: [-40],
  alltime_peak_db: [-38],
}

const mockActivity: ActivityData = {
  frequency_mhz: [144.0],
  activity_pct: [75],
}

describe('useHeatmap', () => {
  it('returns null data when no band is selected', () => {
    const { result } = renderHook(() => useHeatmap())
    expect(result.current.data).toBeNull()
    expect(api.fetchHeatmap).not.toHaveBeenCalled()
  })

  it('fetches data when bandId is set', async () => {
    vi.mocked(api.fetchHeatmap).mockResolvedValue(mockHeatmap)
    useStore.setState({ bandId: 'band-1' })

    const { result } = renderHook(() => useHeatmap())
    await waitFor(() => expect(result.current.data).toEqual(mockHeatmap))
    expect(api.fetchHeatmap).toHaveBeenCalledWith('band-1', expect.any(String))
  })

  it('sets error=true when fetch fails', async () => {
    vi.mocked(api.fetchHeatmap).mockRejectedValue(new Error('network error'))
    useStore.setState({ bandId: 'band-1' })

    const { result } = renderHook(() => useHeatmap())
    await waitFor(() => expect(result.current.error).toBe(true))
    expect(result.current.data).toBeNull()
  })

  it('resets data to null when bandId changes', async () => {
    vi.mocked(api.fetchHeatmap).mockResolvedValue(mockHeatmap)
    useStore.setState({ bandId: 'band-1' })

    const { result } = renderHook(() => useHeatmap())
    await waitFor(() => expect(result.current.data).not.toBeNull())

    // Change band — data should clear before new fetch resolves
    vi.mocked(api.fetchHeatmap).mockReturnValue(new Promise(() => {}))  // pending forever
    useStore.setState({ bandId: 'band-2' })
    await waitFor(() => expect(result.current.data).toBeNull())
  })

  it('passes freq filters in the query string', async () => {
    vi.mocked(api.fetchHeatmap).mockResolvedValue(mockHeatmap)
    useStore.setState({ bandId: 'band-1', filters: { freq_min: 144, freq_max: 146 } })

    renderHook(() => useHeatmap())
    await waitFor(() => expect(api.fetchHeatmap).toHaveBeenCalled())

    const qs = vi.mocked(api.fetchHeatmap).mock.calls[0][1]
    expect(qs).toContain('freq_min=144')
    expect(qs).toContain('freq_max=146')
  })
})

describe('useSpectrum', () => {
  it('returns null when no band selected', () => {
    const { result } = renderHook(() => useSpectrum())
    expect(result.current.data).toBeNull()
  })

  it('fetches spectrum data for selected band', async () => {
    vi.mocked(api.fetchSpectrum).mockResolvedValue(mockSpectrum)
    useStore.setState({ bandId: 'band-1' })

    const { result } = renderHook(() => useSpectrum())
    await waitFor(() => expect(result.current.data).toEqual(mockSpectrum))
  })
})

describe('useActivity', () => {
  it('includes threshold in query string', async () => {
    vi.mocked(api.fetchActivity).mockResolvedValue(mockActivity)
    useStore.setState({ bandId: 'band-1', threshold: -5 })

    renderHook(() => useActivity())
    await waitFor(() => expect(api.fetchActivity).toHaveBeenCalled())

    const qs = vi.mocked(api.fetchActivity).mock.calls[0][1]
    expect(qs).toContain('threshold=-5')
  })
})

describe('live mode behaviour', () => {
  it('does not reset data on filter change in live mode', async () => {
    vi.mocked(api.fetchHeatmap).mockResolvedValue(mockHeatmap)
    useStore.setState({ bandId: 'band-1', timeRange: '1m', filters: {} })

    const { result } = renderHook(() => useHeatmap())
    await waitFor(() => expect(result.current.data).not.toBeNull())

    // In live mode, filter changes go to tickDeps — data should stay non-null
    vi.mocked(api.fetchHeatmap).mockResolvedValue(mockHeatmap)
    useStore.setState({ filters: { freq_min: 144 } })

    // Give React a moment to process; data should not have been cleared to null
    await waitFor(() => expect(result.current.data).not.toBeNull())
  })
})
