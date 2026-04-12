import { useEffect, useState } from 'react'
import { useStore } from './store'
import { api } from './api'
import BandTable from './components/BandTable'
import BandModal from './components/BandModal'
import FilterPanel from './components/FilterPanel'
import Heatmap from './components/Heatmap'
import TimeseriesChart from './components/charts/TimeseriesChart'
import SpectrumChart from './components/charts/SpectrumChart'
import ActivityChart from './components/charts/ActivityChart'
import TodHeatmap from './components/charts/TodHeatmap'
import DurationChart from './components/charts/DurationChart'
import StatusModal from './components/StatusModal'
import ChartFullscreen from './components/ChartFullscreen'

export default function App() {
  const bands        = useStore(s => s.bands)
  const bandId       = useStore(s => s.bandId)
  const setBandId    = useStore(s => s.setBandId)
  const setDevices   = useStore(s => s.setDevices)
  const tick         = useStore(s => s.tick)
  const analysisTick = useStore(s => s.analysisTick)
  const [statusOpen, setStatusOpen] = useState(false)

  // Load devices once on mount
  useEffect(() => {
    api.fetchDevices().then(setDevices).catch(console.error)
  }, [])

  // Poll: main charts every 15s, analysis charts every 60s
  useEffect(() => {
    const t1 = setInterval(tick,         15_000)
    const t2 = setInterval(analysisTick, 60_000)
    return () => { clearInterval(t1); clearInterval(t2) }
  }, [])

  const running = bands.filter(b => b.status === 'running').map(b => b.name)
  const statusText = running.length ? `Running: ${running.join(', ')}` : 'No active captures'

  return (
    <div className="container-fluid py-3">
      {/* Header */}
      <div className="row mb-3 align-items-center">
        <div className="col text-center">
          <h4 className="mb-0 fw-bold">RTL Power Dashboard</h4>
        </div>
        <div className="col-auto position-absolute end-0 pe-3">
          <button
            className="btn btn-outline-secondary btn-sm"
            title="Backend status"
            onClick={() => setStatusOpen(true)}
          >
            ⚙ Status
          </button>
        </div>
      </div>

      <StatusModal open={statusOpen} onClose={() => setStatusOpen(false)} />

      {/* Band management */}
      <BandTable />
      <BandModal />

      {/* Band selector + status */}
      <div id="band-view" className="row mb-2 align-items-end">
        <div className="col-md-4 col-sm-6">
          <label className="form-label mb-1 small text-muted">Viewing band</label>
          <select
            className="form-select form-select-sm"
            value={bandId ?? ''}
            onChange={e => setBandId(e.target.value || null)}
          >
            <option value="">Select a band…</option>
            {bands.map(b => (
              <option key={b.id} value={b.id}>{b.name}</option>
            ))}
          </select>
        </div>
        <div className="col-md-8 col-sm-6">
          <span className="text-muted small">{statusText}</span>
        </div>
      </div>

      {/* Filters */}
      <FilterPanel />

      {/* Analysis charts: ToD occupancy + Signal duration */}
      <div className="row mb-3">
        <div className="col-md-6 mb-2">
          <ChartFullscreen><TodHeatmap /></ChartFullscreen>
        </div>
        <div className="col-md-6 mb-2">
          <ChartFullscreen><DurationChart /></ChartFullscreen>
        </div>
      </div>

      {/* Heatmap (includes colorbar) */}
      <ChartFullscreen><Heatmap /></ChartFullscreen>

      {/* Timeseries (appears after clicking heatmap) */}
      <ChartFullscreen><TimeseriesChart /></ChartFullscreen>

      {/* Spectrum + Activity */}
      <div className="row mb-1">
        <div className="col-12">
          <h6 className="mb-2 text-muted">Frequency Usage</h6>
        </div>
      </div>
      <div className="row">
        <div className="col-md-6 mb-3">
          <ChartFullscreen><SpectrumChart /></ChartFullscreen>
        </div>
        <div className="col-md-6 mb-3">
          <ChartFullscreen><ActivityChart /></ChartFullscreen>
        </div>
      </div>
    </div>
  )
}
