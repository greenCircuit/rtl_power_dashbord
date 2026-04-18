import { create } from 'zustand'
import type { Band, Device, Filters, HeatmapLayout } from './api'

interface AppState {
  // Data
  bands: Band[]
  devices: Device[]

  // Viewing
  bandId: string | null
  selectedFreq: number | null
  heatmapLayout: HeatmapLayout | null

  // Filters
  filters: Filters
  threshold: number
  timeRange: string

  // Polling ticks — incremented on interval; charts depend on these to refetch
  refreshTick: number
  analysisRefreshTick: number
  pollInterval: number  // ms; 0 = paused

  // Band modal
  modalOpen: boolean
  editingId: string | null

  // Actions
  setBands: (bands: Band[]) => void
  setDevices: (devices: Device[]) => void
  setBandId: (id: string | null) => void
  setSelectedFreq: (freq: number | null) => void
  setHeatmapLayout: (layout: HeatmapLayout | null) => void
  setFilters: (filters: Filters) => void
  setThreshold: (t: number) => void
  setTimeRange: (range: string) => void
  setPollInterval: (ms: number) => void
  tick: () => void
  analysisTick: () => void
  openAddModal: () => void
  openEditModal: (id: string) => void
  closeModal: () => void
}

export const useStore = create<AppState>((set) => ({
  bands: [],
  devices: [{ index: 0, name: 'Device 0' }],
  bandId: null,
  selectedFreq: null,
  heatmapLayout: null,
  filters: {},
  threshold: 0,
  timeRange: '12h',
  refreshTick: 0,
  analysisRefreshTick: 0,
  pollInterval: 15_000,
  modalOpen: false,
  editingId: null,

  setBands:         (bands)         => set({ bands }),
  setDevices:       (devices)       => set({ devices }),
  setBandId:        (bandId)        => set({ bandId, selectedFreq: null }),
  setSelectedFreq:  (selectedFreq)  => set({ selectedFreq }),
  setHeatmapLayout: (heatmapLayout) => set({ heatmapLayout }),
  setFilters:       (filters)       => set({ filters }),
  setThreshold:     (threshold)     => set({ threshold }),
  setTimeRange:     (timeRange)     => set({ timeRange }),
  setPollInterval:  (pollInterval)  => set({ pollInterval }),
  tick:             ()              => set(s => ({ refreshTick: s.refreshTick + 1 })),
  analysisTick:     ()              => set(s => ({ analysisRefreshTick: s.analysisRefreshTick + 1 })),
  openAddModal:     ()              => set({ modalOpen: true,  editingId: null }),
  openEditModal:    (editingId)     => set({ modalOpen: true,  editingId }),
  closeModal:       ()              => set({ modalOpen: false, editingId: null }),
}))
