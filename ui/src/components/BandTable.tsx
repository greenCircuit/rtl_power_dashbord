import { useEffect } from 'react'
import { useStore } from '../store'
import { api } from '../api'

const STATUS_COLOR: Record<string, string> = {
  running:   'success',
  idle:      'secondary',
  stopped:   'warning',
  completed: 'info',
  error:     'danger',
}

export default function BandTable() {
  const bands        = useStore(s => s.bands)
  const setBands     = useStore(s => s.setBands)
  const refreshTick  = useStore(s => s.refreshTick)
  const openAddModal = useStore(s => s.openAddModal)
  const openEditModal = useStore(s => s.openEditModal)
  const tick         = useStore(s => s.tick)
  const setBandId    = useStore(s => s.setBandId)
  const currentBandId = useStore(s => s.bandId)

  useEffect(() => {
    api.fetchBands().then(setBands).catch(console.error)
  }, [refreshTick])

  async function toggleBand(id: string, isRunning: boolean) {
    // Optimistic update so the header status text changes immediately
    setBands(bands.map(b => b.id === id ? { ...b, status: isRunning ? 'idle' : 'running' } : b))
    try {
      if (isRunning) await api.stopBand(id)
      else           await api.startBand(id)
    } catch (e) {
      console.warn('toggleBand:', e)
    }
    tick() // Reconcile with real server state
  }

  async function deleteBand(id: string) {
    if (!confirm('Delete this band and all its data?')) return
    try {
      await api.deleteBand(id)
    } catch (e) {
      console.warn('deleteBand:', e)
    }
    if (currentBandId === id) setBandId(null)
    tick()
  }

  return (
    <div className="card mb-3">
      <div className="card-body">
        <div className="d-flex align-items-center mb-2 gap-2">
          <span className="fw-bold">Bands</span>
          <button className="btn btn-primary btn-sm" onClick={openAddModal}>
            + Add Band
          </button>
        </div>

        {bands.length === 0 ? (
          <span className="text-muted small">
            No bands configured. Click &ldquo;+ Add Band&rdquo; to get started.
          </span>
        ) : (
          <div className="table-responsive">
            <table className="table table-sm table-hover mb-0">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Freq Range</th>
                  <th>Step</th>
                  <th>Interval</th>
                  <th>Min Power</th>
                  <th>Device</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {bands.map(b => {
                  const isRunning = b.status === 'running'
                  const color = STATUS_COLOR[b.status] ?? 'secondary'
                  return (
                    <tr key={b.id}>
                      <td className="fw-semibold">{b.name}</td>
                      <td>{b.freq_start} – {b.freq_end}</td>
                      <td>{b.freq_step}</td>
                      <td>{b.interval_s} s</td>
                      <td>{b.min_power} dB</td>
                      <td>{b.device_name ?? `Device ${b.device_index}`}</td>
                      <td>
                        <span className={`badge bg-${color}${isRunning ? ' fs-6 px-2 py-1' : ''}`}>
                          {isRunning && '● '}{b.status}
                        </span>
                      </td>
                      <td>
                        <div className="btn-group btn-group-sm">
                          <button
                            className={`btn btn-${isRunning ? 'danger' : 'success'}`}
                            onClick={() => toggleBand(b.id, isRunning)}
                          >
                            {isRunning ? '■ Stop' : '▶ Start'}
                          </button>
                          <button
                            className="btn btn-info ms-1"
                            onClick={() => {
                              setBandId(b.id)
                              // scroll to charts
                              document.getElementById('band-view')?.scrollIntoView({ behavior: 'smooth' })
                            }}
                          >
                            View
                          </button>
                          <button
                            className="btn btn-secondary ms-1"
                            onClick={() => openEditModal(b.id)}
                          >
                            Edit
                          </button>
                          <button
                            className="btn btn-outline-danger ms-1"
                            onClick={() => deleteBand(b.id)}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
