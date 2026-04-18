import { useState, useCallback, useEffect, useRef } from 'react'
import { useStore } from '../store'
import type { Filters } from '../api'

const RANGE_OFFSETS: Record<string, number> = {
  '1m':  60,
  '15m': 15 * 60,
  '1h':  3600,
  '12h': 12 * 3600,
  '1d':  86400,
  '7d':  7 * 86400,
}
const RANGES = ['1m', '15m', '1h', '12h', '1d', '7d', 'all']

const POLL_OPTIONS = [
  { label: 'Off', ms: 0       },
  { label: '5s',  ms: 5_000   },
  { label: '10s', ms: 10_000  },
  { label: '15s', ms: 15_000  },
  { label: '30s', ms: 30_000  },
  { label: '1m',  ms: 60_000  },
  { label: '5m',  ms: 300_000 },
]

function pad(n: number) { return String(n).padStart(2, '0') }

// For the datetime-local input display (local time, minutes precision is fine for UI)
function toLocalDT(d: Date) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// DB stores UTC; convert any local datetime string to a UTC filter value.
// Also adds seconds so time_max doesn't cut off data in the current minute.
function toUtcFilter(d: Date): string {
  return d.toISOString().replace('T', ' ').slice(0, 19)
}

export default function FilterPanel() {
  const setFilters      = useStore(s => s.setFilters)
  const setThreshold    = useStore(s => s.setThreshold)
  const threshold       = useStore(s => s.threshold)
  const timeRange       = useStore(s => s.timeRange)
  const setTimeRange    = useStore(s => s.setTimeRange)
  const pollInterval    = useStore(s => s.pollInterval)
  const setPollInterval = useStore(s => s.setPollInterval)

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
    if (tStart)      f.time_min = toUtcFilter(new Date(tStart))
    if (tEnd)        f.time_max = toUtcFilter(new Date(tEnd))
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
      // Display inputs show local time; backend receives UTC with seconds precision.
      setTimeStart(toLocalDT(start))
      setTimeEnd(toLocalDT(now))
      const f: Filters = { time_min: toUtcFilter(start), time_max: toUtcFilter(now) }
      const cur = buildFilters({ timeStart: '', timeEnd: '' })
      if (cur.freq_min != null) f.freq_min = cur.freq_min
      if (cur.freq_max != null) f.freq_max = cur.freq_max
      setFilters(f)
    }
  }

  // Live mode: keep the 1-minute window rolling every 5 s.
  // We use a ref so the interval callback always sees the latest applyRange
  // without re-registering the interval on every render.
  const applyRangeRef = useRef(applyRange)
  useEffect(() => { applyRangeRef.current = applyRange })

  useEffect(() => {
    if (timeRange !== '1m') return
    const id = setInterval(() => applyRangeRef.current('1m'), 5_000)
    return () => clearInterval(id)
  }, [timeRange])

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
                  className={`btn btn-range${
                    timeRange === r
                      ? r === '1m' ? ' btn-danger active' : ' btn-outline-secondary active'
                      : r === '1m' ? ' btn-outline-danger' : ' btn-outline-secondary'
                  }`}
                  onClick={() => applyRange(r)}
                >
                  {r === '1m' && timeRange === '1m'
                    ? <><span className="live-dot" /> Live</>
                    : r === '1m' ? '1m live' : r}
                </button>
              ))}
            </div>
          </div>

          {/* Refresh interval */}
          <div className="col-auto d-flex align-items-end gap-1">
            <label className="form-label mb-0 small text-muted" style={{ whiteSpace: 'nowrap' }}>
              ↻ Refresh
            </label>
            <select
              className="form-select form-select-sm"
              style={{ width: 'auto' }}
              value={pollInterval}
              onChange={e => setPollInterval(Number(e.target.value))}
            >
              {POLL_OPTIONS.map(o => (
                <option key={o.ms} value={o.ms}>{o.label}</option>
              ))}
            </select>
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
