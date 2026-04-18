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
import PowerHistogramChart from './components/charts/PowerHistogramChart'
import TopChannelsChart from './components/charts/TopChannelsChart'
import ActivityTrendChart from './components/charts/ActivityTrendChart'
import NoiseFloorChart from './components/charts/NoiseFloorChart'
import StatusModal from './components/StatusModal'
import ChartFullscreen from './components/ChartFullscreen'

export default function App() {
  const bands        = useStore(s => s.bands)
  const bandId       = useStore(s => s.bandId)
  const setBandId    = useStore(s => s.setBandId)
  const setDevices   = useStore(s => s.setDevices)
  const tick         = useStore(s => s.tick)
  const analysisTick = useStore(s => s.analysisTick)
  const pollInterval = useStore(s => s.pollInterval)
  const [statusOpen, setStatusOpen] = useState(false)

  // Load devices once on mount
  useEffect(() => {
    api.fetchDevices().then(setDevices).catch(console.error)
  }, [])

  // Poll: main charts at pollInterval, analysis at 4× (min 60s). 0 = paused.
  useEffect(() => {
    if (pollInterval === 0) return
    const t1 = setInterval(tick,         pollInterval)
    const t2 = setInterval(analysisTick, Math.max(pollInterval * 4, 60_000))
    return () => { clearInterval(t1); clearInterval(t2) }
  }, [pollInterval])

  const selectedBand = bands.find(b => b.id === bandId)

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
        <div className="col-md-8 col-sm-6 d-flex align-items-center gap-2">
          {selectedBand ? (
            <span className="fw-semibold">Capturing {selectedBand.name}</span>
          ) : (
            <span className="text-muted small">No active captures</span>
          )}
        </div>
      </div>

      {/* Filters */}
      <FilterPanel />

      {/* Analysis charts row 1: ToD occupancy + Signal duration */}
      <div className="row mb-3">
        <div className="col-md-6 mb-2">
          <ChartFullscreen><TodHeatmap /></ChartFullscreen>
        </div>
        <div className="col-md-6 mb-2">
          <ChartFullscreen><DurationChart /></ChartFullscreen>
        </div>
      </div>

      {/* Analysis charts row 2: Activity trend + Noise floor envelope */}
      <div className="row mb-3">
        <div className="col-md-6 mb-2">
          <ChartFullscreen><ActivityTrendChart /></ChartFullscreen>
        </div>
        <div className="col-md-6 mb-2">
          <ChartFullscreen><NoiseFloorChart /></ChartFullscreen>
        </div>
      </div>

      {/* Top active channels + Power distribution */}
      <div className="row mb-3">
        <div className="col-md-6 mb-2">
          <ChartFullscreen><TopChannelsChart /></ChartFullscreen>
        </div>
        <div className="col-md-6 mb-2">
          <ChartFullscreen><PowerHistogramChart /></ChartFullscreen>
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
