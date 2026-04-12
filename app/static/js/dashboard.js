/* RTL Power Dashboard — Chart.js + Bootstrap frontend */

// ── Plasma colorscale (sampled from matplotlib plasma) ────────────────────────
const PLASMA = [
  [13,   8,  135],
  [75,   3,  161],
  [125,  3,  168],
  [168, 34,  150],
  [203, 70,  121],
  [229, 107,  93],
  [248, 148,  65],
  [253, 195,  40],
  [240, 243,  33],
];

function plasmaColor(t) {
  const n = PLASMA.length - 1;
  const scaled = Math.max(0, Math.min(1, t)) * n;
  const i = Math.floor(scaled);
  const f = scaled - i;
  const a = PLASMA[Math.min(i,     n)];
  const b = PLASMA[Math.min(i + 1, n)];
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ];
}

// ── YlOrRd colorscale (for ToD heatmap) ──────────────────────────────────────
const YLORRD = [
  [255, 255, 204],
  [255, 237, 160],
  [254, 217, 118],
  [254, 178,  76],
  [253, 141,  60],
  [252,  78,  42],
  [227,  26,  28],
  [177,   0,  38],
];

function ylorrdColor(t) {
  const n = YLORRD.length - 1;
  const s = Math.max(0, Math.min(1, t)) * n;
  const i = Math.floor(s), f = s - i;
  const a = YLORRD[Math.min(i, n)], b = YLORRD[Math.min(i + 1, n)];
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ];
}

// ── Global state ──────────────────────────────────────────────────────────────
const state = {
  bandId:      null,
  editingId:   null,   // null = adding new, string = editing existing
  filters:     {},
  timeRange:   '12h',
  heatmap:     null,   // last drawn heatmap data + layout info
  devices:     [],     // [{index, name}] from /api/devices
  charts: {
    spectrum:   null,
    activity:   null,
    timeseries: null,
    duration:   null,
  },
};

// ── Device helpers ────────────────────────────────────────────────────────────
async function fetchDevices() {
  try {
    const data = await apiFetch('/api/devices');
    state.devices = data.devices || [];
  } catch (e) {
    console.error('fetchDevices failed:', e);
    state.devices = [{ index: 0, name: 'Device 0' }];
  }
  const sel = document.getElementById('modal-device-index');
  if (sel) {
    sel.innerHTML = state.devices
      .map(d => `<option value="${d.index}">${esc(d.name)}</option>`)
      .join('');
  }
}

function deviceName(index) {
  const i = Number(index);
  const d = state.devices.find(d => d.index === i);
  return d ? d.name : `Device ${i}`;
}

// ── DOM helpers ───────────────────────────────────────────────────────────────
function esc(s) {
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function show(el, visible) {
  if (typeof el === 'string') el = document.getElementById(el);
  el.style.display = visible ? '' : 'none';
}

function showEmpty(section, msg) {
  const empty  = document.getElementById(`${section}-empty`);
  const canvas = document.getElementById(`${section}-canvas`);
  if (empty)  { empty.textContent = msg; show(empty, true); }
  if (canvas) { show(canvas, false); }
}

function hideEmpty(section) {
  const empty  = document.getElementById(`${section}-empty`);
  const canvas = document.getElementById(`${section}-canvas`);
  if (empty)  show(empty, false);
  if (canvas) show(canvas, true);
}

// ── Chart.js defaults ─────────────────────────────────────────────────────────
Chart.defaults.color = '#aaa';
Chart.defaults.borderColor = '#2a2a2a';

const CHART_BASE_OPTS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  plugins: {
    legend: { labels: { color: '#ccc', boxWidth: 12 } },
  },
};

function darkScales(xLabel, yLabel, extraX = {}, extraY = {}) {
  return {
    x: {
      ticks: { color: '#999', maxTicksLimit: 8 },
      grid:  { color: '#222' },
      title: { display: !!xLabel, text: xLabel, color: '#888' },
      ...extraX,
    },
    y: {
      ticks: { color: '#999' },
      grid:  { color: '#222' },
      title: { display: !!yLabel, text: yLabel, color: '#888' },
      ...extraY,
    },
  };
}

// ── API helpers ───────────────────────────────────────────────────────────────
async function apiFetch(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function filtersToQS(extra = {}) {
  const p = new URLSearchParams({ ...state.filters, ...extra });
  return p.toString() ? '?' + p.toString() : '';
}

// ── Band list & table ─────────────────────────────────────────────────────────
const STATUS_BADGE = {
  running:   'success',
  idle:      'secondary',
  stopped:   'warning',
  completed: 'info',
  error:     'danger',
};

function renderBandTable(bands) {
  const wrap = document.getElementById('band-table-wrap');
  if (!bands.length) {
    wrap.innerHTML = '<span class="text-muted small">No bands configured. Click "+ Add Band" to get started.</span>';
    return;
  }

  const rows = bands.map(b => {
    const color = STATUS_BADGE[b.status] || 'secondary';
    const isRunning = b.status === 'running';
    return `
      <tr>
        <td class="fw-semibold">${esc(b.name)}</td>
        <td>${esc(b.freq_start)} – ${esc(b.freq_end)}</td>
        <td>${esc(b.freq_step)}</td>
        <td>${esc(b.interval_s)} s</td>
        <td>${esc(b.min_power)} dB</td>
        <td>${esc(b.device_name || b.device_index)}</td>
        <td><span class="badge bg-${color}">${esc(b.status)}</span></td>
        <td>
          <div class="btn-group btn-group-sm">
            <button class="btn btn-${isRunning ? 'danger' : 'success'}"
                    onclick="toggleBand('${esc(b.id)}','${isRunning}')">
              ${isRunning ? '■ Stop' : '▶ Start'}
            </button>
            <button class="btn btn-info ms-1" onclick="viewBand('${esc(b.id)}')">View</button>
            <button class="btn btn-secondary ms-1" onclick="openEditModal('${esc(b.id)}')">Edit</button>
            <button class="btn btn-outline-danger ms-1" onclick="deleteBand('${esc(b.id)}')">Delete</button>
          </div>
        </td>
      </tr>`;
  }).join('');

  wrap.innerHTML = `
    <div class="table-responsive">
      <table class="table table-sm table-hover mb-0">
        <thead><tr>
          <th>Name</th><th>Freq Range</th><th>Step</th>
          <th>Interval</th><th>Min Power</th><th>Device</th>
          <th>Status</th><th>Actions</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function updateBandDropdown(bands) {
  const sel = document.getElementById('band-select');
  const current = sel.value;
  sel.innerHTML = '<option value="">Select a band…</option>' +
    bands.map(b => `<option value="${esc(b.id)}" ${b.id === current ? 'selected' : ''}>${esc(b.name)}</option>`).join('');
}


async function fetchBands() {
  try {
    const data = await apiFetch('/api/bands');
    const bands = data.bands;
    renderBandTable(bands);
    updateBandDropdown(bands);

    const running = bands.filter(b => b.status === 'running').map(b => b.name);
    document.getElementById('status-text').textContent =
      running.length ? `Running: ${running.join(', ')}` : 'No active captures';
  } catch (e) {
    console.error('fetchBands:', e);
  }
}

// ── Band CRUD actions (called from table HTML) ────────────────────────────────
async function toggleBand(id, isRunning) {
  const action = isRunning === 'true' ? 'stop' : 'start';
  try {
    await apiFetch(`/api/bands/${id}/${action}`, { method: 'POST' });
  } catch (e) {
    console.warn('toggleBand:', e);
  }
  fetchBands();
}

function viewBand(id) {
  const sel = document.getElementById('band-select');
  sel.value = id;
  sel.dispatchEvent(new Event('change'));
}

async function deleteBand(id) {
  if (!confirm('Delete this band and all its data?')) return;
  try {
    await apiFetch(`/api/bands/${id}`, { method: 'DELETE' });
  } catch (e) {
    console.warn('deleteBand:', e);
  }
  if (state.bandId === id) {
    state.bandId = null;
    document.getElementById('band-select').value = '';
    clearCharts();
  }
  fetchBands();
}

// ── Band modal ────────────────────────────────────────────────────────────────
const bandModal = new bootstrap.Modal(document.getElementById('band-modal'));

function splitFreq(s) {
  for (const u of ['G', 'M', 'k']) {
    if (String(s).endsWith(u)) return [s.slice(0, -1), u];
  }
  return [s, 'M'];
}

function openAddModal() {
  state.editingId = null;
  document.getElementById('modal-title').textContent = 'Add Band';
  document.getElementById('modal-name').value         = '';
  document.getElementById('modal-freq-start').value   = '88';
  document.getElementById('modal-freq-start-unit').value = 'M';
  document.getElementById('modal-freq-end').value     = '108';
  document.getElementById('modal-freq-end-unit').value   = 'M';
  document.getElementById('modal-freq-step').value    = '0.2';
  document.getElementById('modal-freq-step-unit').value  = 'M';
  document.getElementById('modal-interval').value     = '10';
  document.getElementById('modal-min-power').value    = '2';
  document.getElementById('modal-device-index').value = '0';
  document.getElementById('modal-error').textContent  = '';
  bandModal.show();
}

async function openEditModal(id) {
  try {
    const bands = (await apiFetch('/api/bands')).bands;
    const b = bands.find(x => x.id === id);
    if (!b) return;

    state.editingId = id;
    document.getElementById('modal-title').textContent = `Edit Band — ${b.name}`;
    document.getElementById('modal-name').value        = b.name;

    const [fsV, fsU] = splitFreq(b.freq_start);
    const [feV, feU] = splitFreq(b.freq_end);
    const [fstV, fstU] = splitFreq(b.freq_step);

    document.getElementById('modal-freq-start').value      = fsV;
    document.getElementById('modal-freq-start-unit').value = fsU;
    document.getElementById('modal-freq-end').value        = feV;
    document.getElementById('modal-freq-end-unit').value   = feU;
    document.getElementById('modal-freq-step').value       = fstV;
    document.getElementById('modal-freq-step-unit').value  = fstU;
    document.getElementById('modal-interval').value        = b.interval_s;
    document.getElementById('modal-min-power').value       = b.min_power;
    document.getElementById('modal-device-index').value    = b.device_index;
    document.getElementById('modal-error').textContent     = '';
    bandModal.show();
  } catch (e) {
    console.error('openEditModal:', e);
  }
}

async function saveBand() {
  const name      = document.getElementById('modal-name').value.trim();
  const fsVal     = document.getElementById('modal-freq-start').value;
  const fsUnit    = document.getElementById('modal-freq-start-unit').value;
  const feVal     = document.getElementById('modal-freq-end').value;
  const feUnit    = document.getElementById('modal-freq-end-unit').value;
  const fstVal    = document.getElementById('modal-freq-step').value;
  const fstUnit   = document.getElementById('modal-freq-step-unit').value;
  const interval  = document.getElementById('modal-interval').value;
  const minPower  = document.getElementById('modal-min-power').value;
  const devIdx    = document.getElementById('modal-device-index').value;
  const errEl     = document.getElementById('modal-error');

  if (!name || !fsVal || !feVal || !fstVal) {
    errEl.textContent = 'All frequency fields are required.';
    return;
  }

  const body = {
    name,
    freq_start:   `${fsVal}${fsUnit}`,
    freq_end:     `${feVal}${feUnit}`,
    freq_step:    `${fstVal}${fstUnit}`,
    interval_s:   parseInt(interval || 10),
    min_power:    parseFloat(minPower || 2),
    device_index: parseInt(devIdx || 0),
  };

  try {
    if (state.editingId) {
      await apiFetch(`/api/bands/${state.editingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } else {
      await apiFetch('/api/bands', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    }
    bandModal.hide();
    fetchBands();
  } catch (e) {
    errEl.textContent = e.message || 'Save failed.';
  }
}

// ── Filter & time-range ───────────────────────────────────────────────────────
const RANGE_OFFSETS = {
  '15m': 15 * 60,
  '1h':  3600,
  '12h': 12 * 3600,
  '1d':  24 * 3600,
  '7d':  7 * 24 * 3600,
};

function toLocalDT(d) {
  // Format a Date as a datetime-local string (no seconds)
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function applyTimeRange(range) {
  state.timeRange = range;

  // Update button styles
  document.querySelectorAll('.btn-range').forEach(btn => {
    const active = btn.dataset.range === range;
    btn.classList.toggle('active', active);
    btn.classList.toggle('btn-outline-secondary', !active);
  });

  if (range === 'all') {
    document.getElementById('filter-time-start').value = '';
    document.getElementById('filter-time-end').value   = '';
    delete state.filters.time_min;
    delete state.filters.time_max;
  } else {
    const secs = RANGE_OFFSETS[range];
    if (!secs) return;
    const now   = new Date();
    const start = new Date(now.getTime() - secs * 1000);
    document.getElementById('filter-time-start').value = toLocalDT(start);
    document.getElementById('filter-time-end').value   = toLocalDT(now);
    state.filters.time_min = toLocalDT(start).replace('T', ' ');
    state.filters.time_max = toLocalDT(now).replace('T', ' ');
  }

  if (state.bandId) fetchAllCharts();
}

function collectFilters() {
  const fMin = document.getElementById('filter-freq-min').value;
  const fMax = document.getElementById('filter-freq-max').value;
  const tMin = document.getElementById('filter-time-start').value;
  const tMax = document.getElementById('filter-time-end').value;
  const pMin = parseInt(document.getElementById('filter-power-min').value);

  const f = {};
  if (fMin !== '') f.freq_min = fMin;
  if (fMax !== '') f.freq_max = fMax;
  if (tMin)       f.time_min = tMin.replace('T', ' ');
  if (tMax)       f.time_max = tMax.replace('T', ' ');
  if (pMin > -20) f.power_min = pMin;

  state.filters = f;
  if (state.bandId) fetchAllCharts();
}

function clearFilters() {
  document.getElementById('filter-freq-min').value   = '';
  document.getElementById('filter-freq-max').value   = '';
  document.getElementById('filter-time-start').value = '';
  document.getElementById('filter-time-end').value   = '';
  document.getElementById('filter-power-min').value  = '-20';
  document.getElementById('power-min-label').textContent = '−20 dB';

  // Deactivate range buttons
  document.querySelectorAll('.btn-range').forEach(b => {
    b.classList.remove('active');
    b.classList.add('btn-outline-secondary');
  });
  state.timeRange = null;
  state.filters   = {};
  if (state.bandId) fetchAllCharts();
}

// ── Heatmap (canvas) ──────────────────────────────────────────────────────────
const MARGIN = { top: 30, right: 10, bottom: 50, left: 65 };

function drawColorbar(zMin, zMax) {
  const cbWrap  = document.getElementById('colorbar-wrap');
  const cbCanvas = document.getElementById('colorbar-canvas');
  show(cbWrap, true);

  const dpr = window.devicePixelRatio || 1;
  cbCanvas.width  = Math.round(cbCanvas.offsetWidth  * dpr);
  cbCanvas.height = Math.round(cbCanvas.offsetHeight * dpr);
  const ctx = cbCanvas.getContext('2d');

  const H = cbCanvas.height;
  const W = cbCanvas.width;
  const img = ctx.createImageData(W, H);
  for (let py = 0; py < H; py++) {
    const t = 1 - py / H;
    const [r, g, b] = plasmaColor(t);
    for (let px = 0; px < W; px++) {
      const i = (py * W + px) * 4;
      img.data[i]   = r;
      img.data[i+1] = g;
      img.data[i+2] = b;
      img.data[i+3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);

  document.getElementById('cb-max').textContent = zMax.toFixed(1);
  document.getElementById('cb-min').textContent = zMin.toFixed(1);
}

function drawHeatmap(data) {
  const canvas  = document.getElementById('heatmap-canvas');
  const wrap    = document.getElementById('heatmap-wrap');
  const emptyEl = document.getElementById('heatmap-empty');
  show(emptyEl, false);

  // Use the wrap element for reliable rendered dimensions
  const dpr = window.devicePixelRatio || 1;
  const rect = wrap.getBoundingClientRect();
  const W0 = rect.width  || wrap.offsetWidth  || 800;
  const H0 = rect.height || wrap.offsetHeight || 480;

  canvas.width  = Math.round(W0 * dpr);
  canvas.height = Math.round(H0 * dpr);

  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const W = W0;
  const H = H0;
  const { top, right, bottom, left } = MARGIN;
  const plotW = W - left - right;
  const plotH = H - top  - bottom;
  const nTime = data.x.length;
  const nFreq = data.y.length;

  // z range
  let zMin = Infinity, zMax = -Infinity;
  for (let fi = 0; fi < nFreq; fi++) {
    const row = data.z[fi];
    for (let ti = 0; ti < nTime; ti++) {
      const v = row[ti];
      if (v != null && isFinite(v)) {
        if (v < zMin) zMin = v;
        if (v > zMax) zMax = v;
      }
    }
  }
  const zRange = zMax > zMin ? zMax - zMin : 1;

  // Render heatmap pixels onto offscreen canvas
  const ow = Math.max(1, Math.floor(plotW));
  const oh = Math.max(1, Math.floor(plotH));
  const offscreen = document.createElement('canvas');
  offscreen.width  = ow;
  offscreen.height = oh;
  const octx = offscreen.getContext('2d');
  const img  = octx.createImageData(ow, oh);

  for (let py = 0; py < oh; py++) {
    const fi = Math.max(0, Math.min(Math.floor((1 - py / oh) * nFreq), nFreq - 1));
    const row = data.z[fi];
    for (let px = 0; px < ow; px++) {
      const ti = Math.max(0, Math.min(Math.floor(px / ow * nTime), nTime - 1));
      const v  = row[ti];
      const i  = (py * ow + px) * 4;
      if (v === null || v === undefined) {
        img.data[i] = img.data[i+1] = img.data[i+2] = 20;  // dark grey for no-data
        img.data[i+3] = 255;
      } else {
        const [r, g, b] = plasmaColor((v - zMin) / zRange);
        img.data[i]   = r;
        img.data[i+1] = g;
        img.data[i+2] = b;
        img.data[i+3] = 255;
      }
    }
  }
  octx.putImageData(img, 0, 0);

  // Background
  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, W, H);

  // Clip to plot area and draw heatmap
  ctx.save();
  ctx.beginPath();
  ctx.rect(left, top, plotW, plotH);
  ctx.clip();
  ctx.drawImage(offscreen, left, top, plotW, plotH);
  ctx.restore();

  // Grid lines + axis labels
  ctx.fillStyle   = '#ccc';
  ctx.strokeStyle = '#333';
  ctx.lineWidth   = 0.5;
  ctx.font        = '11px monospace';

  // Y axis (frequency)
  ctx.textAlign = 'right';
  const nYTicks = 6;
  for (let i = 0; i <= nYTicks; i++) {
    const t    = i / nYTicks;
    const fi   = Math.max(0, Math.min(Math.floor(t * (nFreq - 1)), nFreq - 1));
    const freq = data.y[fi];
    const y    = top + plotH * (1 - t);
    ctx.fillText(freq != null ? freq.toFixed(2) : '', left - 5, y + 4);
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(left + plotW, y);
    ctx.stroke();
  }

  // X axis (time)
  ctx.textAlign = 'center';
  const nXTicks = 5;
  for (let i = 0; i <= nXTicks; i++) {
    const t   = i / nXTicks;
    const ti  = Math.max(0, Math.min(Math.floor(t * (nTime - 1)), nTime - 1));
    const lbl = data.x[ti] ? String(data.x[ti]).substring(11, 16) : '';
    const x   = left + plotW * t;
    ctx.fillText(lbl, x, top + plotH + 16);
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, top + plotH);
    ctx.stroke();
  }

  // Axis border
  ctx.strokeStyle = '#555';
  ctx.lineWidth   = 1;
  ctx.strokeRect(left, top, plotW, plotH);

  // Y axis title
  ctx.save();
  ctx.translate(13, top + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = 'center';
  ctx.fillStyle = '#aaa';
  ctx.font      = '11px sans-serif';
  ctx.fillText('Frequency (MHz)', 0, 0);
  ctx.restore();

  // X axis title
  ctx.fillStyle = '#aaa';
  ctx.font      = '11px sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('Time', left + plotW / 2, H - 6);

  // Title
  ctx.fillStyle = '#ddd';
  ctx.font      = '13px sans-serif';
  ctx.fillText('Spectrum Heatmap', left + plotW / 2, 18);

  // Store layout for mouse events
  state.heatmap = { data, zMin, zMax, left, top, plotW, plotH, nTime, nFreq, W0, H0 };

  drawColorbar(zMin, zMax);
}

function showHeatmapEmpty(msg) {
  const emptyEl = document.getElementById('heatmap-empty');
  emptyEl.textContent = msg;
  show(emptyEl, true);
  show('colorbar-wrap', false);

  // Clear canvas
  const canvas = document.getElementById('heatmap-canvas');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  state.heatmap = null;
}

// Heatmap mouse events
function setupHeatmapEvents() {
  const canvas     = document.getElementById('heatmap-canvas');
  const crosshair  = document.getElementById('heatmap-crosshair');
  const tooltip    = document.getElementById('heatmap-tooltip');

  function clearCrosshair() {
    const ctx = crosshair.getContext('2d');
    ctx.clearRect(0, 0, crosshair.width, crosshair.height);
  }

  function drawCrosshair(crossX, crossY, h) {
    const { left, top, plotW, plotH } = h;
    const dpr = window.devicePixelRatio || 1;
    // Keep crosshair canvas in sync with main canvas dimensions
    if (crosshair.width !== canvas.width || crosshair.height !== canvas.height) {
      crosshair.width  = canvas.width;
      crosshair.height = canvas.height;
    }
    const ctx = crosshair.getContext('2d');
    ctx.clearRect(0, 0, crosshair.width, crosshair.height);
    ctx.save();
    ctx.scale(dpr, dpr);
    ctx.strokeStyle = 'rgba(255,255,255,0.35)';
    ctx.lineWidth   = 1;
    ctx.setLineDash([4, 4]);
    // Horizontal line (frequency)
    ctx.beginPath();
    ctx.moveTo(left, crossY);
    ctx.lineTo(left + plotW, crossY);
    ctx.stroke();
    // Vertical line (time)
    ctx.beginPath();
    ctx.moveTo(crossX, top);
    ctx.lineTo(crossX, top + plotH);
    ctx.stroke();
    // Small dot at intersection
    ctx.setLineDash([]);
    ctx.strokeStyle = 'rgba(255,255,255,0.75)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(crossX, crossY, 3, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  canvas.addEventListener('mousemove', e => {
    const h = state.heatmap;
    if (!h) { clearCrosshair(); show(tooltip, false); return; }
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const { left, top, plotW, plotH, nTime, nFreq } = h;

    if (mx < left || mx > left + plotW || my < top || my > top + plotH) {
      clearCrosshair();
      show(tooltip, false);
      return;
    }

    const ti = Math.max(0, Math.min(Math.floor((mx - left) / plotW * nTime), nTime - 1));
    const fi = Math.max(0, Math.min(Math.floor((1 - (my - top) / plotH) * nFreq), nFreq - 1));

    const freq  = h.data.y[fi];
    const time  = h.data.x[ti];
    const power = h.data.z[fi] != null ? h.data.z[fi][ti] : null;

    // Draw crosshair at the snapped cell centre
    const crossX = left + (ti + 0.5) / nTime * plotW;
    const crossY = top  + (1 - (fi + 0.5) / nFreq) * plotH;
    drawCrosshair(crossX, crossY, h);

    // Build tooltip HTML
    const freqStr  = freq  != null ? freq.toFixed(3) + ' MHz'  : '—';
    const powerStr = power != null ? power.toFixed(1) + ' dBFS' : '—';
    const timeStr  = time  ? String(time).substring(0, 19)      : '—';
    tooltip.innerHTML =
      `<span style="color:#aaa;font-size:10px">${timeStr}</span><br>` +
      `<b style="color:#7cf">${freqStr}</b>&nbsp;&nbsp;` +
      `<b style="color:#fc8">${powerStr}</b>`;

    // Position: prefer right-of-cursor, flip left if near right edge
    const wrapRect = canvas.parentElement.getBoundingClientRect();
    const TW = 210;
    let tx = e.clientX - wrapRect.left + 14;
    let ty = e.clientY - wrapRect.top  - 44;
    if (tx + TW > wrapRect.width)  tx = e.clientX - wrapRect.left - TW - 10;
    if (ty < 4) ty = ty + 50;
    tooltip.style.left = tx + 'px';
    tooltip.style.top  = ty + 'px';
    show(tooltip, true);
  });

  canvas.addEventListener('mouseleave', () => {
    clearCrosshair();
    show(tooltip, false);
  });

  canvas.addEventListener('click', e => {
    const h = state.heatmap;
    if (!h) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const { left, top, plotW, plotH, nFreq } = h;

    if (mx < left || mx > left + plotW || my < top || my > top + plotH) return;

    const fi   = Math.max(0, Math.min(Math.floor((1 - (my - top) / plotH) * nFreq), nFreq - 1));
    const freq = h.data.y[fi];
    if (freq != null) fetchTimeseries(freq);
  });
}

// ── Timeseries chart ──────────────────────────────────────────────────────────
async function fetchTimeseries(freqMhz) {
  if (!state.bandId) return;
  try {
    const qs   = filtersToQS({ freq_mhz: freqMhz });
    const data = await apiFetch(`/api/bands/${state.bandId}/timeseries${qs}`);
    updateTimeseriesChart(data);
  } catch {
    showEmpty('timeseries', `No data for ${freqMhz.toFixed(3)} MHz`);
  }
}

function updateTimeseriesChart(data) {
  hideEmpty('timeseries');
  const canvas = document.getElementById('timeseries-canvas');
  const labels = data.timestamps.map(t => String(t).substring(11, 19));

  if (state.charts.timeseries) {
    const ch = state.charts.timeseries;
    ch.data.labels        = labels;
    ch.data.datasets[0].data = data.power_db;
    ch.options.plugins.title.text = `Power over time — ${data.frequency_mhz} MHz`;
    ch.update();
    return;
  }

  state.charts.timeseries = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: `${data.frequency_mhz} MHz`,
        data: data.power_db,
        borderColor: '#f0a500',
        borderWidth: 1.5,
        pointRadius: 2,
        tension: 0.2,
        fill: false,
      }],
    },
    options: {
      ...CHART_BASE_OPTS,
      scales: darkScales('Time', 'Power (dBFS)'),
      plugins: {
        ...CHART_BASE_OPTS.plugins,
        title: { display: true, text: `Power over time — ${data.frequency_mhz} MHz`, color: '#ccc' },
        tooltip: {
          callbacks: { label: ctx => `${ctx.parsed.y.toFixed(1)} dBFS` },
        },
      },
    },
  });
}

// ── Spectrum chart ────────────────────────────────────────────────────────────
function updateSpectrumChart(data) {
  hideEmpty('spectrum');
  const canvas = document.getElementById('spectrum-canvas');
  const labels = data.frequency_mhz;

  if (state.charts.spectrum) {
    const ch = state.charts.spectrum;
    ch.data.labels           = labels;
    ch.data.datasets[0].data = data.mean_db;
    ch.data.datasets[1].data = data.peak_db;
    ch.update();
    return;
  }

  state.charts.spectrum = new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Mean power',
          data: data.mean_db,
          borderColor: '#4fc3f7',
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.1,
        },
        {
          label: 'Peak power',
          data: data.peak_db,
          borderColor: '#ff7043',
          borderWidth: 1,
          borderDash: [5, 5],
          pointRadius: 0,
          tension: 0.1,
        },
      ],
    },
    options: {
      ...CHART_BASE_OPTS,
      scales: darkScales('Frequency (MHz)', 'Power (dBFS)', {
        ticks: {
          color: '#999',
          maxTicksLimit: 8,
          callback: v => Number(labels[v]).toFixed(2),
        },
      }),
      plugins: {
        ...CHART_BASE_OPTS.plugins,
        title: { display: true, text: 'Mean & Peak Power per Frequency', color: '#ccc' },
        tooltip: {
          callbacks: {
            title: items => `${Number(labels[items[0].dataIndex]).toFixed(3)} MHz`,
            label: ctx  => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} dBFS`,
          },
        },
      },
    },
  });
}

// ── Activity chart ────────────────────────────────────────────────────────────
function updateActivityChart(data) {
  hideEmpty('activity');
  const canvas = document.getElementById('activity-canvas');
  const threshold = getThreshold();
  const labels = data.frequency_mhz;
  const bgColors = data.activity_pct.map(pct => {
    const [r, g, b] = plasmaColor(Math.max(0, Math.min(1, pct / 100 * 0.85 + 0.05)));
    return `rgb(${r},${g},${b})`;
  });

  if (state.charts.activity) {
    const ch = state.charts.activity;
    ch.data.labels                        = labels;
    ch.data.datasets[0].data              = data.activity_pct;
    ch.data.datasets[0].backgroundColor   = bgColors;
    ch.options.plugins.title.text         = `Activity above ${threshold} dBFS`;
    ch.update();
    return;
  }

  state.charts.activity = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Active time (%)',
        data: data.activity_pct,
        backgroundColor: bgColors,
        borderWidth: 0,
        barPercentage: 1.0,
        categoryPercentage: 1.0,
      }],
    },
    options: {
      ...CHART_BASE_OPTS,
      scales: darkScales('Frequency (MHz)', 'Time active (%)', {
        ticks: {
          color: '#999',
          maxTicksLimit: 8,
          callback: v => Number(labels[v]).toFixed(2),
        },
      }, { min: 0, max: 100 }),
      plugins: {
        ...CHART_BASE_OPTS.plugins,
        title: { display: true, text: `Activity above ${threshold} dBFS`, color: '#ccc' },
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: items => `${Number(labels[items[0].dataIndex]).toFixed(3)} MHz`,
            label: ctx  => `Active: ${ctx.parsed.y.toFixed(1)}%`,
          },
        },
      },
    },
  });
}

function destroyChart(key) {
  if (state.charts[key]) {
    state.charts[key].destroy();
    state.charts[key] = null;
  }
}

function clearCharts() {
  destroyChart('spectrum');
  destroyChart('activity');
  destroyChart('timeseries');
  destroyChart('duration');
  showHeatmapEmpty('No band selected');
  showEmpty('spectrum',   'No band selected');
  showEmpty('activity',   'No band selected');
  showEmpty('timeseries', 'Click a frequency on the heatmap to see power over time');
  clearTodCanvas();
  showEmpty('tod',      'No band selected');
  showEmpty('duration', 'No band selected');
}

function getThreshold() {
  return parseInt(document.getElementById('threshold').value, 10);
}


// ── ToD occupancy heatmap (canvas) ────────────────────────────────────────────
const TOD_MARGIN = { top: 28, right: 12, bottom: 36, left: 40 };

function clearTodCanvas() {
  const canvas = document.getElementById('tod-canvas');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  show('tod-canvas', false);
}

function drawTodHeatmap(data) {
  // data: { z: [7][24], y: ['Sun'..], x: [0..23] }
  const wrap   = document.getElementById('tod-wrap');
  const canvas = document.getElementById('tod-canvas');
  show(canvas, true);
  show('tod-empty', false);

  const dpr  = window.devicePixelRatio || 1;
  const W0   = wrap.offsetWidth  || 600;
  const H0   = wrap.offsetHeight || 320;
  canvas.width  = Math.round(W0 * dpr);
  canvas.height = Math.round(H0 * dpr);
  canvas.style.width  = W0 + 'px';
  canvas.style.height = H0 + 'px';

  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const { top, right, bottom, left } = TOD_MARGIN;
  const plotW = W0 - left - right;
  const plotH = H0 - top  - bottom;
  const nHours = 24, nDays = 7;
  const cW = plotW / nHours;
  const cH = plotH / nDays;

  ctx.fillStyle = '#111';
  ctx.fillRect(0, 0, W0, H0);

  // Cells
  for (let d = 0; d < nDays; d++) {
    for (let h = 0; h < nHours; h++) {
      const pct = data.z[d][h];
      const [r, g, b] = ylorrdColor(pct / 100);
      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.fillRect(left + h * cW, top + d * cH, cW, cH);
    }
  }

  // Grid
  ctx.strokeStyle = '#111';
  ctx.lineWidth   = 0.5;
  for (let h = 0; h <= nHours; h++) {
    ctx.beginPath();
    ctx.moveTo(left + h * cW, top);
    ctx.lineTo(left + h * cW, top + plotH);
    ctx.stroke();
  }
  for (let d = 0; d <= nDays; d++) {
    ctx.beginPath();
    ctx.moveTo(left, top + d * cH);
    ctx.lineTo(left + plotW, top + d * cH);
    ctx.stroke();
  }

  // Y axis labels (days)
  ctx.fillStyle  = '#ccc';
  ctx.font       = '11px sans-serif';
  ctx.textAlign  = 'right';
  ctx.textBaseline = 'middle';
  for (let d = 0; d < nDays; d++) {
    ctx.fillText(data.y[d], left - 4, top + d * cH + cH / 2);
  }

  // X axis labels (hours, every 2)
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'top';
  for (let h = 0; h < nHours; h += 2) {
    ctx.fillText(h, left + h * cW + cW, top + plotH + 4);
  }

  // Title
  ctx.fillStyle    = '#ddd';
  ctx.font         = '12px sans-serif';
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'alphabetic';
  ctx.fillText('Time-of-Day Occupancy (%)', left + plotW / 2, top - 8);

  // X axis title
  ctx.fillStyle = '#888';
  ctx.font      = '10px sans-serif';
  ctx.fillText('Hour of day', left + plotW / 2, H0 - 3);
}


// ── Signal duration histogram ─────────────────────────────────────────────────
function updateDurationChart(data) {
  // data: { bins, counts, total, min_s, max_s }
  if (!data.bins.length) { showEmpty('duration', 'No transmissions detected'); return; }
  hideEmpty('duration');
  const canvas = document.getElementById('duration-canvas');
  show(canvas, true);

  const labels    = data.bins.map(v => v.toFixed(1));
  const threshold = getThreshold();

  if (state.charts.duration) {
    const ch = state.charts.duration;
    ch.data.labels           = labels;
    ch.data.datasets[0].data = data.counts;
    ch.options.plugins.title.text = `Signal Durations above ${threshold} dBFS (n=${data.total})`;
    ch.update();
    return;
  }

  state.charts.duration = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Count',
        data: data.counts,
        backgroundColor: '#ab47bc',
        borderWidth: 0,
        barPercentage: 1.0,
        categoryPercentage: 1.0,
      }],
    },
    options: {
      ...CHART_BASE_OPTS,
      scales: darkScales('Duration (s)', 'Count'),
      plugins: {
        ...CHART_BASE_OPTS.plugins,
        legend: { display: false },
        title: { display: true, text: `Signal Durations above ${threshold} dBFS (n=${data.total})`, color: '#ccc' },
        tooltip: {
          callbacks: { label: ctx => `${ctx.parsed.y} transmissions` },
        },
      },
    },
  });
}

// ── Fetch analysis charts (ToD + duration) ────────────────────────────────────
async function fetchAnalysisCharts() {
  if (!state.bandId) return;
  const threshold = getThreshold();
  const qs        = filtersToQS({ threshold });

  // Time-of-day occupancy heatmap
  (async () => {
    try {
      const data = await apiFetch(`/api/bands/${state.bandId}/tod-activity${qs}`);
      drawTodHeatmap(data);
    } catch {
      clearTodCanvas();
      show('tod-empty', true);
      showEmpty('tod', 'No data yet');
    }
  })();

  // Signal duration histogram
  (async () => {
    try {
      const data = await apiFetch(`/api/bands/${state.bandId}/signal-durations${qs}`);
      updateDurationChart(data);
    } catch {
      showEmpty('duration', 'No transmissions detected above threshold');
    }
  })();
}

// ── Fetch all chart data for current band ─────────────────────────────────────
async function fetchAllCharts() {
  if (!state.bandId) return;
  const id = state.bandId;
  const qs = filtersToQS();

  // Heatmap
  (async () => {
    try {
      const data = await apiFetch(`/api/bands/${id}/heatmap${qs}`);
      if (state.bandId === id) drawHeatmap(data);
    } catch (e) {
      console.error('heatmap error:', e);
      if (state.bandId === id) showHeatmapEmpty('No data yet');
    }
  })();

  // Spectrum
  (async () => {
    try {
      const data = await apiFetch(`/api/bands/${id}/spectrum${qs}`);
      if (state.bandId === id) updateSpectrumChart(data);
    } catch {
      if (state.bandId === id) showEmpty('spectrum', 'No data yet');
    }
  })();

  // Activity
  (async () => {
    const threshold = getThreshold();
    try {
      const data = await apiFetch(`/api/bands/${id}/activity${filtersToQS({ threshold })}`);
      if (state.bandId === id) updateActivityChart(data);
    } catch {
      if (state.bandId === id) showEmpty('activity', 'No data yet');
    }
  })();
}

// ── Debounce helper ───────────────────────────────────────────────────────────
function debounce(fn, ms) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
}

// ── Init ──────────────────────────────────────────────────────────────────────
function init() {
  setupHeatmapEvents();

  // Band add / save
  document.getElementById('btn-add-band').addEventListener('click', openAddModal);
  document.getElementById('btn-modal-save').addEventListener('click', saveBand);

  // Band select dropdown
  document.getElementById('band-select').addEventListener('change', e => {
    const id = e.target.value;
    if (!id) {
      state.bandId = null;
      clearCharts();
      return;
    }
    if (id !== state.bandId) {
      state.bandId = id;
      destroyChart('timeseries');
      destroyChart('duration');
      showEmpty('timeseries', 'Click a frequency on the heatmap to see power over time');
      fetchAllCharts();
      fetchAnalysisCharts();  // ToD + duration refresh on band change
    }
  });

  // Time range buttons
  document.querySelectorAll('.btn-range').forEach(btn => {
    btn.addEventListener('click', () => applyTimeRange(btn.dataset.range));
  });

  // Filter inputs (debounced)
  const debouncedFilter = debounce(collectFilters, 600);
  ['filter-freq-min', 'filter-freq-max', 'filter-time-start', 'filter-time-end']
    .forEach(id => document.getElementById(id).addEventListener('change', debouncedFilter));

  // Power slider
  const powerSlider = document.getElementById('filter-power-min');
  const powerLabel  = document.getElementById('power-min-label');
  powerSlider.addEventListener('input', () => {
    powerLabel.textContent = `${powerSlider.value} dB`;
  });
  powerSlider.addEventListener('change', debouncedFilter);

  // Clear filters
  document.getElementById('btn-filter-clear').addEventListener('click', clearFilters);

  // Global activity threshold slider
  const threshSlider = document.getElementById('threshold');
  const threshLabel  = document.getElementById('threshold-label');
  threshSlider.addEventListener('input', () => {
    threshLabel.textContent = `${threshSlider.value} dB`;
  });
  threshSlider.addEventListener('change', () => {
    if (!state.bandId) return;
    const id = state.bandId;
    const qs = filtersToQS({ threshold: threshSlider.value });
    apiFetch(`/api/bands/${id}/activity${qs}`)
      .then(data => { if (state.bandId === id) updateActivityChart(data); })
      .catch(() => {});
    destroyChart('duration');
    fetchAnalysisCharts();
  });

  applyTimeRange('12h');

  // Fetch device list once on load (populates modal select + band table names)
  fetchDevices().then(fetchBands);

  // Redraw heatmap on resize
  const heatmapWrap = document.getElementById('heatmap-wrap');
  const ro = new ResizeObserver(debounce(() => {
    if (state.heatmap) drawHeatmap(state.heatmap.data);
  }, 300));
  ro.observe(heatmapWrap);

  // Poll main charts every 15 seconds
  setInterval(() => {
    fetchBands();
    if (state.bandId) fetchAllCharts();
  }, 15000);

  // Poll analysis charts (expensive) every 60 seconds
  setInterval(() => {
    if (state.bandId) fetchAnalysisCharts();
  }, 60000);
}

document.addEventListener('DOMContentLoaded', init);
