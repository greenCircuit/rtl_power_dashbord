import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import FilterPanel from '../components/FilterPanel'
import { useStore } from '../store'

const INITIAL = useStore.getState()

beforeEach(() => {
  useStore.setState(INITIAL, true)
})

describe('FilterPanel — time range buttons', () => {
  it('renders all time range shortcuts', () => {
    render(<FilterPanel />)
    for (const label of ['1m live', '15m', '1h', '12h', '1d', '7d', 'all']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('clicking 15m sets timeRange to "15m" in store', () => {
    render(<FilterPanel />)
    fireEvent.click(screen.getByText('15m'))
    expect(useStore.getState().timeRange).toBe('15m')
  })

  it('clicking 1h sets timeRange to "1h" in store', () => {
    render(<FilterPanel />)
    fireEvent.click(screen.getByText('1h'))
    expect(useStore.getState().timeRange).toBe('1h')
  })

  it('clicking 7d sets timeRange to "7d" in store', () => {
    render(<FilterPanel />)
    fireEvent.click(screen.getByText('7d'))
    expect(useStore.getState().timeRange).toBe('7d')
  })

  it('clicking all clears time filters', () => {
    useStore.setState({ filters: { time_min: '2024-01-01 00:00:00' } })
    render(<FilterPanel />)
    fireEvent.click(screen.getByText('all'))
    expect(useStore.getState().timeRange).toBe('all')
    expect(useStore.getState().filters.time_min).toBeUndefined()
    expect(useStore.getState().filters.time_max).toBeUndefined()
  })

  it('clicking a range button sets time_min and time_max in filters', () => {
    render(<FilterPanel />)
    fireEvent.click(screen.getByText('1h'))
    const { time_min, time_max } = useStore.getState().filters
    expect(time_min).toBeDefined()
    expect(time_max).toBeDefined()
  })

  it('range button preserves existing freq filters', () => {
    render(<FilterPanel />)
    // Set freq filters via the inputs
    fireEvent.change(screen.getByPlaceholderText('e.g. 88'), { target: { value: '88' } })
    fireEvent.click(screen.getByText('1h'))
    expect(useStore.getState().filters.freq_min).toBe(88)
  })
})

describe('FilterPanel — live mode interval', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('rolls the 1m window every 5 seconds in live mode', () => {
    vi.useFakeTimers()
    useStore.setState({ timeRange: '1m' })
    render(<FilterPanel />)

    const filtersBefore = { ...useStore.getState().filters }
    vi.advanceTimersByTime(5_000)

    const filtersAfter = useStore.getState().filters
    // time_max should have advanced (re-calculated from new Date())
    expect(filtersAfter.time_max).not.toBe(filtersBefore.time_max)
  })

  it('does not start live interval when timeRange is not 1m', () => {
    vi.useFakeTimers()
    const setFiltersSpy = vi.spyOn(useStore.getState(), 'setFilters')
    render(<FilterPanel />)  // default timeRange is 12h

    vi.advanceTimersByTime(10_000)
    expect(setFiltersSpy).not.toHaveBeenCalled()
  })
})

describe('FilterPanel — refresh interval dropdown', () => {
  it('renders refresh dropdown with default 15s selected', () => {
    render(<FilterPanel />)
    const select = screen.getByDisplayValue('15s')
    expect(select).toBeInTheDocument()
  })

  it('changing dropdown updates pollInterval in store', () => {
    render(<FilterPanel />)
    const select = screen.getByDisplayValue('15s')
    fireEvent.change(select, { target: { value: '5000' } })
    expect(useStore.getState().pollInterval).toBe(5_000)
  })

  it('selecting Off sets pollInterval to 0', () => {
    render(<FilterPanel />)
    const select = screen.getByDisplayValue('15s')
    fireEvent.change(select, { target: { value: '0' } })
    expect(useStore.getState().pollInterval).toBe(0)
  })
})

describe('FilterPanel — activity threshold', () => {
  it('renders threshold slider', () => {
    render(<FilterPanel />)
    expect(screen.getByRole('slider')).toBeInTheDocument()
  })

  it('moving slider updates threshold in store', () => {
    render(<FilterPanel />)
    const slider = screen.getByRole('slider')
    fireEvent.change(slider, { target: { value: '-10' } })
    expect(useStore.getState().threshold).toBe(-10)
  })

  it('displays current threshold value as badge', () => {
    useStore.setState({ threshold: 5 })
    render(<FilterPanel />)
    expect(screen.getByText('+5 dB')).toBeInTheDocument()
  })
})

describe('FilterPanel — clear button', () => {
  it('resets timeRange to "all" and clears filters', () => {
    render(<FilterPanel />)
    fireEvent.click(screen.getByText('1h'))
    fireEvent.click(screen.getByText('Clear'))
    const s = useStore.getState()
    expect(s.timeRange).toBe('all')
    expect(s.filters).toEqual({})
  })
})
