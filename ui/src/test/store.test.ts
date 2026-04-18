import { describe, it, expect, beforeEach } from 'vitest'
import { useStore } from '../store'

// Capture initial state (including action references) before any test mutates it
const INITIAL = useStore.getState()

beforeEach(() => {
  useStore.setState(INITIAL, true)
})

describe('initial state', () => {
  it('has correct defaults', () => {
    const s = useStore.getState()
    expect(s.bands).toEqual([])
    expect(s.bandId).toBeNull()
    expect(s.selectedFreq).toBeNull()
    expect(s.threshold).toBe(0)
    expect(s.timeRange).toBe('12h')
    expect(s.refreshTick).toBe(0)
    expect(s.analysisRefreshTick).toBe(0)
    expect(s.pollInterval).toBe(15_000)
    expect(s.modalOpen).toBe(false)
    expect(s.editingId).toBeNull()
  })
})

describe('setBandId', () => {
  it('sets bandId', () => {
    useStore.getState().setBandId('band-1')
    expect(useStore.getState().bandId).toBe('band-1')
  })

  it('clears selectedFreq when band changes', () => {
    useStore.setState({ selectedFreq: 144.5 })
    useStore.getState().setBandId('band-1')
    expect(useStore.getState().selectedFreq).toBeNull()
  })

  it('accepts null to deselect', () => {
    useStore.setState({ bandId: 'band-1' })
    useStore.getState().setBandId(null)
    expect(useStore.getState().bandId).toBeNull()
  })
})

describe('tick / analysisTick', () => {
  it('tick increments refreshTick', () => {
    useStore.getState().tick()
    expect(useStore.getState().refreshTick).toBe(1)
    useStore.getState().tick()
    expect(useStore.getState().refreshTick).toBe(2)
  })

  it('analysisTick increments analysisRefreshTick', () => {
    useStore.getState().analysisTick()
    expect(useStore.getState().analysisRefreshTick).toBe(1)
  })

  it('tick and analysisTick are independent', () => {
    useStore.getState().tick()
    useStore.getState().tick()
    useStore.getState().analysisTick()
    expect(useStore.getState().refreshTick).toBe(2)
    expect(useStore.getState().analysisRefreshTick).toBe(1)
  })
})

describe('setPollInterval', () => {
  it('updates pollInterval', () => {
    useStore.getState().setPollInterval(5_000)
    expect(useStore.getState().pollInterval).toBe(5_000)
  })

  it('accepts 0 to pause polling', () => {
    useStore.getState().setPollInterval(0)
    expect(useStore.getState().pollInterval).toBe(0)
  })
})

describe('setThreshold', () => {
  it('updates threshold', () => {
    useStore.getState().setThreshold(-10)
    expect(useStore.getState().threshold).toBe(-10)
  })
})

describe('setFilters', () => {
  it('updates filters', () => {
    useStore.getState().setFilters({ freq_min: 88, freq_max: 108 })
    expect(useStore.getState().filters).toEqual({ freq_min: 88, freq_max: 108 })
  })

  it('replaces previous filters entirely', () => {
    useStore.getState().setFilters({ freq_min: 88 })
    useStore.getState().setFilters({ freq_max: 108 })
    expect(useStore.getState().filters).toEqual({ freq_max: 108 })
  })
})

describe('modal actions', () => {
  it('openAddModal opens modal with no editingId', () => {
    useStore.getState().openAddModal()
    const s = useStore.getState()
    expect(s.modalOpen).toBe(true)
    expect(s.editingId).toBeNull()
  })

  it('openEditModal opens modal with editingId set', () => {
    useStore.getState().openEditModal('band-1')
    const s = useStore.getState()
    expect(s.modalOpen).toBe(true)
    expect(s.editingId).toBe('band-1')
  })

  it('closeModal resets modal state', () => {
    useStore.setState({ modalOpen: true, editingId: 'band-1' })
    useStore.getState().closeModal()
    const s = useStore.getState()
    expect(s.modalOpen).toBe(false)
    expect(s.editingId).toBeNull()
  })
})
