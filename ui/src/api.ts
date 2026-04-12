// ── API types ─────────────────────────────────────────────────────────────────

export interface Band {
  id: string
  name: string
  freq_start: string
  freq_end: string
  freq_step: string
  interval_s: number
  min_power: number
  device_index: number
  is_active: boolean
  status: string
  device_name?: string
}

export interface Device {
  index: number
  name: string
}

export interface Filters {
  freq_min?: number
  freq_max?: number
  time_min?: string
  time_max?: string
}

export interface HeatmapData {
  x: string[]
  y: number[]
  z: (number | null)[][]
  freq_min: number
  freq_max: number
  time_min: string
  time_max: string
}

export interface HeatmapLayout {
  data: HeatmapData
  zMin: number
  zMax: number
  left: number
  top: number
  plotW: number
  plotH: number
  nTime: number
  nFreq: number
  W0: number
  H0: number
}

export interface SpectrumData {
  frequency_mhz: number[]
  mean_db: number[]
  peak_db: number[]
}

export interface ActivityData {
  frequency_mhz: number[]
  activity_pct: number[]
}

export interface TimeseriesData {
  frequency_mhz: number
  timestamps: string[]
  power_db: number[]
}

export interface TodData {
  z: number[][]
  x: number[]
  y: string[]
}

export interface DurationData {
  bins: number[]
  counts: number[]
  total: number
  min_s: number
  max_s: number
}

export interface BackendStatus {
  status: string
  demo_mode: boolean
  db_path: string
  db_size_mb: number
  total_measurements: number
  bands: { band_id: string; name: string; count: number; last_seen: string | null }[]
}

export interface BandBody {
  name: string
  freq_start: string
  freq_end: string
  freq_step: string
  interval_s: number
  min_power: number
  device_index: number
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(path, opts)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

export function filtersToQS(
  filters: Filters,
  extra: Record<string, string | number> = {},
): string {
  const p = new URLSearchParams()
  const all = { ...filters, ...extra } as Record<string, string | number | undefined>
  for (const [k, v] of Object.entries(all)) {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  }
  return p.size ? '?' + p.toString() : ''
}

export function splitFreq(s: string): [string, string] {
  for (const u of ['G', 'M', 'k']) {
    if (String(s).endsWith(u)) return [s.slice(0, -1), u]
  }
  return [s, 'M']
}

// ── API calls ─────────────────────────────────────────────────────────────────

const json = (body: unknown) => ({
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  fetchDevices: () =>
    apiFetch<{ devices: Device[] }>('/api/devices').then(r => r.devices),

  fetchBands: () =>
    apiFetch<{ bands: Band[] }>('/api/bands').then(r => r.bands),

  createBand: (body: BandBody) =>
    apiFetch('/api/bands', { method: 'POST', ...json(body) }),

  updateBand: (id: string, body: Partial<BandBody>) =>
    apiFetch(`/api/bands/${id}`, { method: 'PUT', ...json(body) }),

  deleteBand: (id: string) =>
    apiFetch(`/api/bands/${id}`, { method: 'DELETE' }),

  startBand: (id: string) =>
    apiFetch(`/api/bands/${id}/start`, { method: 'POST' }),

  stopBand: (id: string) =>
    apiFetch(`/api/bands/${id}/stop`, { method: 'POST' }),

  fetchHeatmap: (id: string, qs: string) =>
    apiFetch<HeatmapData>(`/api/bands/${id}/heatmap${qs}`),

  fetchSpectrum: (id: string, qs: string) =>
    apiFetch<SpectrumData>(`/api/bands/${id}/spectrum${qs}`),

  fetchActivity: (id: string, qs: string) =>
    apiFetch<ActivityData>(`/api/bands/${id}/activity${qs}`),

  fetchTimeseries: (id: string, qs: string) =>
    apiFetch<TimeseriesData>(`/api/bands/${id}/timeseries${qs}`),

  fetchTodActivity: (id: string, qs: string) =>
    apiFetch<TodData>(`/api/bands/${id}/tod-activity${qs}`),

  fetchDurations: (id: string, qs: string) =>
    apiFetch<DurationData>(`/api/bands/${id}/signal-durations${qs}`),

  fetchStatus: () =>
    apiFetch<BackendStatus>('/api/status'),
}
