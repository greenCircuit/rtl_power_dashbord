import { useEffect, useRef, useState } from 'react'
import Modal from 'bootstrap/js/dist/modal'
import { useStore } from '../store'
import { api, splitFreq } from '../api'

interface FormState {
  name: string
  freqStartVal: string; freqStartUnit: string
  freqEndVal: string;   freqEndUnit: string
  freqStepVal: string;  freqStepUnit: string
  intervalS: string
  minPower: string
  deviceIndex: string
}

const DEFAULT_FORM: FormState = {
  name: '',
  freqStartVal: '88',  freqStartUnit: 'M',
  freqEndVal:   '108', freqEndUnit:   'M',
  freqStepVal:  '0.2', freqStepUnit:  'M',
  intervalS:   '10',
  minPower:    '2',
  deviceIndex: '0',
}

export default function BandModal() {
  const modalOpen  = useStore(s => s.modalOpen)
  const editingId  = useStore(s => s.editingId)
  const closeModal = useStore(s => s.closeModal)
  const devices    = useStore(s => s.devices)
  const bands      = useStore(s => s.bands)
  const tick       = useStore(s => s.tick)

  const [form, setForm]   = useState<FormState>(DEFAULT_FORM)
  const [error, setError] = useState('')

  const modalRef    = useRef<HTMLDivElement>(null)
  const instanceRef = useRef<Modal | null>(null)

  // Bootstrap modal instance lifecycle
  useEffect(() => {
    if (!modalRef.current) return
    instanceRef.current = new Modal(modalRef.current)
    const el = modalRef.current
    const handler = () => closeModal()
    el.addEventListener('hidden.bs.modal', handler)
    return () => {
      el.removeEventListener('hidden.bs.modal', handler)
      instanceRef.current?.dispose()
    }
  }, [])

  // Sync open/close with Bootstrap
  useEffect(() => {
    if (modalOpen) instanceRef.current?.show()
    else           instanceRef.current?.hide()
  }, [modalOpen])

  // Populate form when editing
  useEffect(() => {
    if (!modalOpen) return
    if (editingId) {
      const b = bands.find(x => x.id === editingId)
      if (!b) return
      const [fsV, fsU]   = splitFreq(b.freq_start)
      const [feV, feU]   = splitFreq(b.freq_end)
      const [fstV, fstU] = splitFreq(b.freq_step)
      setForm({
        name: b.name,
        freqStartVal: fsV,  freqStartUnit: fsU,
        freqEndVal:   feV,  freqEndUnit:   feU,
        freqStepVal:  fstV, freqStepUnit:  fstU,
        intervalS:   String(b.interval_s),
        minPower:    String(b.min_power),
        deviceIndex: String(b.device_index),
      })
    } else {
      setForm(DEFAULT_FORM)
    }
    setError('')
  }, [modalOpen, editingId])

  const set = (patch: Partial<FormState>) => setForm(f => ({ ...f, ...patch }))

  async function save() {
    if (!form.name || !form.freqStartVal || !form.freqEndVal || !form.freqStepVal) {
      setError('All frequency fields are required.')
      return
    }
    const body = {
      name:         form.name,
      freq_start:   `${form.freqStartVal}${form.freqStartUnit}`,
      freq_end:     `${form.freqEndVal}${form.freqEndUnit}`,
      freq_step:    `${form.freqStepVal}${form.freqStepUnit}`,
      interval_s:   parseInt(form.intervalS || '10'),
      min_power:    parseFloat(form.minPower || '2'),
      device_index: parseInt(form.deviceIndex || '0'),
    }
    try {
      if (editingId) await api.updateBand(editingId, body)
      else           await api.createBand(body)
      closeModal()
      tick()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed.')
    }
  }

  const unitSelect = (value: string, onChange: (v: string) => void) => (
    <select
      className="form-select"
      style={{ maxWidth: 80 }}
      value={value}
      onChange={e => onChange(e.target.value)}
    >
      <option value="k">kHz</option>
      <option value="M">MHz</option>
      <option value="G">GHz</option>
    </select>
  )

  return (
    <div className="modal fade" ref={modalRef} tabIndex={-1}>
      <div className="modal-dialog modal-lg">
        <div className="modal-content" style={{ background: '#1a1a1a' }}>
          <div className="modal-header">
            <h5 className="modal-title">
              {editingId ? `Edit Band — ${bands.find(b => b.id === editingId)?.name ?? ''}` : 'Add Band'}
            </h5>
            <button type="button" className="btn-close btn-close-white" onClick={closeModal} />
          </div>
          <div className="modal-body">
            <div className="mb-3">
              <label className="form-label">Name</label>
              <input
                type="text"
                className="form-control"
                placeholder="e.g. FM Radio"
                value={form.name}
                onChange={e => set({ name: e.target.value })}
              />
            </div>

            <div className="row g-3 mb-3">
              {([
                ['Freq Start', 'freqStartVal', 'freqStartUnit', '88'],
                ['Freq End',   'freqEndVal',   'freqEndUnit',   '108'],
                ['Step',       'freqStepVal',  'freqStepUnit',  '0.2'],
              ] as const).map(([label, valKey, unitKey, placeholder]) => (
                <div className="col-4" key={label}>
                  <label className="form-label">{label}</label>
                  <div className="input-group">
                    <input
                      type="number"
                      className="form-control"
                      placeholder={placeholder}
                      value={form[valKey]}
                      onChange={e => set({ [valKey]: e.target.value } as Partial<FormState>)}
                    />
                    {unitSelect(form[unitKey], v => set({ [unitKey]: v } as Partial<FormState>))}
                  </div>
                </div>
              ))}
            </div>

            <div className="row g-3 mb-2">
              <div className="col-4">
                <label className="form-label">Interval (s)</label>
                <input type="number" className="form-control" min={1}
                  value={form.intervalS}
                  onChange={e => set({ intervalS: e.target.value })} />
              </div>
              <div className="col-4">
                <label className="form-label">Min Power (dB)</label>
                <input type="number" className="form-control" step={0.5}
                  value={form.minPower}
                  onChange={e => set({ minPower: e.target.value })} />
              </div>
              <div className="col-4">
                <label className="form-label">Device</label>
                <select className="form-select"
                  value={form.deviceIndex}
                  onChange={e => set({ deviceIndex: e.target.value })}>
                  {devices.map(d => (
                    <option key={d.index} value={d.index}>{d.name}</option>
                  ))}
                </select>
              </div>
            </div>

            {error && <div className="text-danger small mt-1">{error}</div>}
          </div>
          <div className="modal-footer">
            <button className="btn btn-secondary" onClick={closeModal}>Cancel</button>
            <button className="btn btn-primary" onClick={save}>Save</button>
          </div>
        </div>
      </div>
    </div>
  )
}
