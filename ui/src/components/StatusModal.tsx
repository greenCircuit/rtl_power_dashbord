import { useEffect, useState } from 'react'
import { api } from '../api'
import type { BackendStatus } from '../api'

function timeAgo(ts: string | null): string {
  if (!ts) return '—'
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000)
  if (diff < 0)   return 'just now'
  if (diff < 60)  return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

interface Props {
  open: boolean
  onClose: () => void
}

export default function StatusModal({ open, onClose }: Props) {
  const [status,  setStatus]  = useState<BackendStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(false)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    setError(false)
    api.fetchStatus()
      .then(s  => { setStatus(s); setLoading(false) })
      .catch(() => { setError(true); setLoading(false) })
  }, [open])

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div className="modal-backdrop fade show" style={{ zIndex: 1040 }} onClick={onClose} />

      <div
        className="modal fade show d-block"
        style={{ zIndex: 1050 }}
        role="dialog"
        aria-modal="true"
      >
        <div className="modal-dialog modal-lg modal-dialog-centered">
          <div className="modal-content bg-dark text-light border-secondary">

            <div className="modal-header border-secondary">
              <h5 className="modal-title">
                Backend Status
                {status && (
                  <span className="ms-2 badge bg-success">● online</span>
                )}
                {status?.demo_mode && (
                  <span className="ms-2 badge bg-warning text-dark">DEMO</span>
                )}
                {error && (
                  <span className="ms-2 badge bg-danger">● unreachable</span>
                )}
              </h5>
              <button type="button" className="btn-close btn-close-white" onClick={onClose} />
            </div>

            <div className="modal-body">
              {loading && (
                <div className="text-center text-muted py-4">Loading…</div>
              )}

              {error && (
                <div className="alert alert-danger">
                  Could not reach the backend. Is the Flask server running?
                </div>
              )}

              {status?.demo_mode && (
                <div className="alert alert-warning d-flex align-items-start gap-2 py-2 mb-3">
                  <span className="fw-bold">Demo mode</span>
                  <span className="text-dark">
                    Synthetic data is being generated from config bands and written to{' '}
                    <code className="text-dark">demo.db</code>. Your live database is not affected.
                    To disable, restart without the <code className="text-dark">DEMO_MODE=true</code> environment variable.
                  </span>
                </div>
              )}

              {status && (
                <>
                  {/* Summary row */}
                  <div className="row g-3 mb-4">
                    <div className="col-sm-4">
                      <div className="border border-secondary rounded p-3 text-center">
                        <div className="fs-4 fw-bold text-info">
                          {status.db_size_mb.toFixed(2)}
                          <span className="fs-6 text-muted ms-1">MB</span>
                        </div>
                        <div className="small text-muted">Database size</div>
                      </div>
                    </div>
                    <div className="col-sm-4">
                      <div className="border border-secondary rounded p-3 text-center">
                        <div className="fs-4 fw-bold text-info">
                          {status.total_measurements.toLocaleString()}
                        </div>
                        <div className="small text-muted">Total measurements</div>
                      </div>
                    </div>
                    <div className="col-sm-4">
                      <div className="border border-secondary rounded p-3 text-center">
                        <div className={`fs-4 fw-bold ${status.demo_mode ? 'text-warning' : 'text-success'}`}>
                          {status.demo_mode ? 'Demo' : 'Live'}
                        </div>
                        <div className="small text-muted">Mode</div>
                      </div>
                    </div>
                  </div>

                  {/* Available devices */}
                  <h6 className="text-muted mb-2">Available devices</h6>
                  {status.devices.length === 0 ? (
                    <p className="text-muted small mb-3">No RTL-SDR devices detected.</p>
                  ) : (
                    <table className="table table-sm table-dark table-bordered mb-3">
                      <thead>
                        <tr>
                          <th style={{ width: '4rem' }}>Index</th>
                          <th>Name</th>
                        </tr>
                      </thead>
                      <tbody>
                        {status.devices.map(d => (
                          <tr key={d.index}>
                            <td className="text-center">{d.index}</td>
                            <td>{d.name}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}

                  {/* Per-band breakdown */}
                  {status.bands.length > 0 && (
                    <>
                      <h6 className="text-muted mb-2">Per-band storage</h6>
                      <table className="table table-sm table-dark table-bordered mb-3">
                        <thead>
                          <tr>
                            <th>Band</th>
                            <th className="text-end">Measurements</th>
                            <th>Last capture</th>
                            <th>Age</th>
                          </tr>
                        </thead>
                        <tbody>
                          {status.bands.map(b => (
                            <tr key={b.band_id}>
                              <td>{b.name}</td>
                              <td className="text-end">{b.count.toLocaleString()}</td>
                              <td className="text-muted small">{b.last_seen ?? '—'}</td>
                              <td className="text-info small">{timeAgo(b.last_seen)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </>
                  )}

                  {/* DB path */}
                  <div className="text-muted small">
                    <span className="me-1">DB path:</span>
                    <code className="text-secondary">{status.db_path}</code>
                  </div>
                </>
              )}
            </div>

            <div className="modal-footer border-secondary">
              <span className="text-muted small me-auto">
                {status?.demo_mode
                  ? <>Demo mode active — set <code>DEMO_MODE=false</code> to return to live capture</>
                  : <>Set <code>DEMO_MODE=true</code> env variable to enable demo mode</>
                }
              </span>
              <button className="btn btn-secondary btn-sm" onClick={onClose}>
                Close
              </button>
            </div>

          </div>
        </div>
      </div>
    </>
  )
}
