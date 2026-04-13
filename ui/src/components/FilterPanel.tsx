import { useState, useCallback } from 'react'
import { useStore } from '../store'
import type { Filters } from '../api'

const RANGE_OFFSETS: Record<string, number> = {
  '15m': 15 * 60,
  '1h':  3600,
  '12h': 12 * 3600,
  '1d':  86400,
  '7d':  7 * 86400,
}
const RANGES = ['15m', '1h', '12h', '1d', '7d', 'all']

function pad(n: number) { return String(n).padStart(2, '0') }
function toLocalDT(d: Date) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export default function FilterPanel() {
  const setFilters   = useStore(s => s.setFilters)
  const setThreshold = useStore(s => s.setThreshold)
  const threshold    = useStore(s => s.threshold)
  const timeRange    = useStore(s => s.timeRange)
  const setTimeRange = useStore(s => s.setTimeRange)

  const [freqMin,   setFreqMin]   = useState('')
  const [freqMax,   setFreqMax]   = useState('')
  const [timeStart, setTimeStart] = useState('')
  const [timeEnd,   setTimeEnd]   = useState('')

  const buildFilters = useCallback((overrides: Partial<{
    freqMin: string; freqMax: string; timeStart: string; timeEnd: string
  }> = {}): Filters => {
    const fMin   = overrides.freqMin   ?? freqMin
    const fMax   = overrides.freqMax   ?? freqMax
    const tStart = overrides.timeStart ?? timeStart
    const tEnd   = overrides.timeEnd   ?? timeEnd
    const f: Filters = {}
    if (fMin !== '') f.freq_min = Number(fMin)
    if (fMax !== '') f.freq_max = Number(fMax)
    if (tStart)      f.time_min = tStart.replace('T', ' ')
    if (tEnd)        f.time_max = tEnd.replace('T', ' ')
    return f
  }, [freqMin, freqMax, timeStart, timeEnd])

  function applyRange(range: string) {
    setTimeRange(range)
    if (range === 'all') {
      setTimeStart(''); setTimeEnd('')
      setFilters(buildFilters({ timeStart: '', timeEnd: '' }))
    } else {
      const secs  = RANGE_OFFSETS[range]
      const now   = new Date()
      const start = new Date(now.getTime() - secs * 1000)
      const s = toLocalDT(start)
      const e = toLocalDT(now)
      setTimeStart(s); setTimeEnd(e)
      setFilters(buildFilters({ timeStart: s, timeEnd: e }))
    }
  }

  function clearFilters() {
    setFreqMin(''); setFreqMax('')
    setTimeStart(''); setTimeEnd('')
    setTimeRange('all')
    setFilters({})
  }

  return (
    <div className="card mb-3 border-secondary sticky-filter" style={{ borderStyle: 'dashed' }}>
      <div className="card-body py-2">
        <div className="row align-items-end g-2 mb-2">
          <div className="col-auto d-flex align-items-end">
            <span className="fw-semibold small">Filters</span>
          </div>

          {/* Time range shortcuts */}
          <div className="col-auto">
            <div className="btn-group btn-group-sm">
              {RANGES.map(r => (
                <button
                  key={r}
                  className={`btn btn-outline-secondary btn-range${timeRange === r ? ' active' : ''}`}
                  onClick={() => applyRange(r)}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>

          {/* Freq min/max */}
          <div className="col-md-2 col-sm-4">
            <label className="form-label mb-1 small">Freq Min (MHz)</label>
            <input type="number" className="form-control form-control-sm" placeholder="e.g. 88"
              value={freqMin}
              onChange={e => { setFreqMin(e.target.value); setFilters(buildFilters({ freqMin: e.target.value })) }} />
          </div>
          <div className="col-md-2 col-sm-4">
            <label className="form-label mb-1 small">Freq Max (MHz)</label>
            <input type="number" className="form-control form-control-sm" placeholder="e.g. 108"
              value={freqMax}
              onChange={e => { setFreqMax(e.target.value); setFilters(buildFilters({ freqMax: e.target.value })) }} />
          </div>

          {/* Time range manual */}
          <div className="col-md-2 col-sm-6">
            <label className="form-label mb-1 small">Time Start</label>
            <input type="datetime-local" className="form-control form-control-sm"
              value={timeStart}
              onChange={e => { setTimeStart(e.target.value); setFilters(buildFilters({ timeStart: e.target.value })) }} />
          </div>
          <div className="col-md-2 col-sm-6">
            <label className="form-label mb-1 small">Time End</label>
            <input type="datetime-local" className="form-control form-control-sm"
              value={timeEnd}
              onChange={e => { setTimeEnd(e.target.value); setFilters(buildFilters({ timeEnd: e.target.value })) }} />
          </div>

          <div className="col-auto">
            <button className="btn btn-secondary btn-sm" onClick={clearFilters}>Clear</button>
          </div>
        </div>

        {/* Activity threshold */}
        <div className="row align-items-center g-2 mt-1">
          <div className="col-auto">
            <span className="slider-label">Activity Threshold (dBFS):</span>
          </div>
          <div className="col-auto">
            <span className="slider-label text-muted">-20</span>
          </div>
          <div className="col">
            <input type="range" className="form-range" min={-20} max={20} step={0.5}
              value={threshold}
              onChange={e => setThreshold(Number(e.target.value))} />
          </div>
          <div className="col-auto">
            <span className="slider-label text-muted">+20</span>
          </div>
          <div className="col-auto" style={{ minWidth: 64 }}>
            <span className="badge bg-secondary fs-6">
              {threshold > 0 ? '+' : ''}{threshold} dB
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
