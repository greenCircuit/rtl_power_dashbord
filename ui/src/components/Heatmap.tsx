import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store'
import { useHeatmap } from '../hooks/useBandData'
import type { HeatmapData, HeatmapLayout } from '../api'
import { plasmaColor } from '../colors'

const MARGIN = { top: 30, right: 10, bottom: 50, left: 65 }

function pad2(n: number) { return String(n).padStart(2, '0') }

// Parse a UTC timestamp string ("YYYY-MM-DD HH:MM:SS") to Unix epoch seconds.
function epochOf(ts: string): number {
  return new Date(ts.replace(' ', 'T') + 'Z').getTime() / 1000
}

// ── Pure drawing functions ────────────────────────────────────────────────────

function buildLayout(canvas: HTMLCanvasElement, data: HeatmapData): HeatmapLayout {
  const wrap = canvas.parentElement!
  const dpr  = window.devicePixelRatio || 1
  const W0   = wrap.getBoundingClientRect().width  || wrap.offsetWidth  || 800
  const H0   = wrap.getBoundingClientRect().height || wrap.offsetHeight || 480

  canvas.width  = Math.round(W0 * dpr)
  canvas.height = Math.round(H0 * dpr)

  const { top, right, bottom, left } = MARGIN
  return {
    data,
    zMin: 0, zMax: 0,  // filled below
    left, top,
    plotW: W0 - left - right,
    plotH: H0 - top  - bottom,
    nTime: data.x.length,
    nFreq: data.y.length,
    W0, H0,
  }
}

function drawHeatmap(
  canvas: HTMLCanvasElement,
  data: HeatmapData,
  rangeStart?: number,   // requested window start (epoch s); undefined = use data range
  rangeEnd?: number,     // requested window end   (epoch s); undefined = use data range
): HeatmapLayout {
  const layout = buildLayout(canvas, data)
  const { left, top, plotW, plotH, nTime, nFreq, W0, H0 } = layout
  const dpr = window.devicePixelRatio || 1
  const ctx = canvas.getContext('2d')!
  ctx.scale(dpr, dpr)

  // Build per-column epoch array for timestamp-based pixel mapping.
  const dataEpochs = data.x.map(ts => epochOf(String(ts)))
  const dataBucketS = nTime > 1
    ? (dataEpochs[nTime - 1] - dataEpochs[0]) / (nTime - 1)
    : 60
  const tMin  = rangeStart ?? dataEpochs[0]          ?? 0
  const tMax  = rangeEnd   ?? dataEpochs[nTime - 1]  ?? tMin + 60
  const tSpan = Math.max(tMax - tMin, 1)

  // z range
  let zMin = Infinity, zMax = -Infinity
  for (const row of data.z) {
    for (const v of row) {
      if (v != null && isFinite(v)) {
        if (v < zMin) zMin = v
        if (v > zMax) zMax = v
      }
    }
  }
  const zRange = zMax > zMin ? zMax - zMin : 1
  layout.zMin = zMin
  layout.zMax = zMax

  // Offscreen pixel render
  const ow = Math.max(1, Math.floor(plotW))
  const oh = Math.max(1, Math.floor(plotH))
  const offscreen = document.createElement('canvas')
  offscreen.width = ow; offscreen.height = oh
  const octx = offscreen.getContext('2d')!
  const img  = octx.createImageData(ow, oh)

  // Pre-compute: for each output pixel column, which data column index to use
  // (or -1 if this pixel falls in a time gap with no nearby data).
  const colMap = new Int32Array(ow)
  for (let px = 0; px < ow; px++) {
    const targetEpoch = tMin + (px / ow) * tSpan
    if (nTime === 0) { colMap[px] = -1; continue }
    // Binary search for the nearest data column.
    let lo = 0, hi = nTime - 1
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (dataEpochs[mid] < targetEpoch) lo = mid + 1; else hi = mid
    }
    if (lo > 0 && Math.abs(dataEpochs[lo - 1] - targetEpoch) < Math.abs(dataEpochs[lo] - targetEpoch)) lo--
    colMap[px] = Math.abs(dataEpochs[lo] - targetEpoch) <= dataBucketS * 0.6 ? lo : -1
  }

  for (let py = 0; py < oh; py++) {
    const fi  = Math.max(0, Math.min(Math.floor((1 - py / oh) * nFreq), nFreq - 1))
    const row = data.z[fi]
    for (let px = 0; px < ow; px++) {
      const ti = colMap[px]
      const v  = ti < 0 ? null : row[ti]
      const i  = (py * ow + px) * 4
      if (v === null || v === undefined) {
        img.data[i] = img.data[i + 1] = img.data[i + 2] = 20
        img.data[i + 3] = 255
      } else {
        const [r, g, b] = plasmaColor((v - zMin) / zRange)
        img.data[i] = r; img.data[i + 1] = g; img.data[i + 2] = b; img.data[i + 3] = 255
      }
    }
  }
  octx.putImageData(img, 0, 0)

  ctx.fillStyle = '#111'
  ctx.fillRect(0, 0, W0, H0)

  ctx.save()
  ctx.beginPath(); ctx.rect(left, top, plotW, plotH); ctx.clip()
  ctx.drawImage(offscreen, left, top, plotW, plotH)
  ctx.restore()

  // Axes
  ctx.fillStyle = '#ccc'; ctx.strokeStyle = '#333'; ctx.lineWidth = 0.5
  ctx.font = '11px monospace'

  // Y axis (frequency)
  ctx.textAlign = 'right'
  for (let i = 0; i <= 6; i++) {
    const t    = i / 6
    const fi   = Math.max(0, Math.min(Math.floor(t * (nFreq - 1)), nFreq - 1))
    const freq = data.y[fi]
    const y    = top + plotH * (1 - t)
    ctx.fillText(freq != null ? freq.toFixed(2) : '', left - 5, y + 4)
    ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(left + plotW, y); ctx.stroke()
  }

  // X axis (time) — labels span the requested range, not just the data range.
  // Use dates for spans >= 2 days, times for shorter spans.
  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
  const useDate = tSpan >= 2 * 86400
  for (let i = 0; i <= 5; i++) {
    const t     = i / 5
    const epoch = tMin + t * tSpan
    const d     = new Date(epoch * 1000)
    const lbl   = useDate
      ? `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`
      : `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`
    const x     = left + plotW * t
    ctx.textAlign = i === 0 ? 'left' : i === 5 ? 'right' : 'center'
    ctx.fillText(lbl, x, top + plotH + 16)
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, top + plotH); ctx.stroke()
  }

  ctx.strokeStyle = '#555'; ctx.lineWidth = 1
  ctx.strokeRect(left, top, plotW, plotH)

  // Axis titles
  ctx.save()
  ctx.translate(13, top + plotH / 2); ctx.rotate(-Math.PI / 2)
  ctx.textAlign = 'center'; ctx.fillStyle = '#aaa'; ctx.font = '11px sans-serif'
  ctx.fillText('Frequency (MHz)', 0, 0)
  ctx.restore()

  ctx.fillStyle = '#aaa'; ctx.font = '11px sans-serif'; ctx.textAlign = 'center'
  ctx.fillText('Time', left + plotW / 2, H0 - 6)

  ctx.fillStyle = '#ddd'; ctx.font = '13px sans-serif'
  ctx.fillText('Spectrum Heatmap', left + plotW / 2, 18)

  return layout
}

function drawColorbar(
  canvas: HTMLCanvasElement,
  zMin: number, zMax: number,
  maxEl: HTMLElement, minEl: HTMLElement,
) {
  const dpr = window.devicePixelRatio || 1
  canvas.width  = Math.round(canvas.offsetWidth  * dpr)
  canvas.height = Math.round(canvas.offsetHeight * dpr)
  const ctx = canvas.getContext('2d')!
  const H = canvas.height, W = canvas.width
  const img = ctx.createImageData(W, H)
  for (let py = 0; py < H; py++) {
    const t = 1 - py / H
    const [r, g, b] = plasmaColor(t)
    for (let px = 0; px < W; px++) {
      const i = (py * W + px) * 4
      img.data[i] = r; img.data[i + 1] = g; img.data[i + 2] = b; img.data[i + 3] = 255
    }
  }
  ctx.putImageData(img, 0, 0)
  maxEl.textContent = zMax.toFixed(1)
  minEl.textContent = zMin.toFixed(1)
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function Heatmap() {
  const bandId    = useStore(s => s.bandId)
  const filters   = useStore(s => s.filters)
  const setLayout = useStore(s => s.setHeatmapLayout)
  const setFreq   = useStore(s => s.setSelectedFreq)

  const { data, error } = useHeatmap()

  // Epoch bounds derived from the active time filter (UTC strings from backend).
  const rangeStart = filters.time_min ? epochOf(filters.time_min) : undefined
  const rangeEnd   = filters.time_max ? epochOf(filters.time_max) : undefined

  const canvasRef    = useRef<HTMLCanvasElement>(null)
  const crossRef     = useRef<HTMLCanvasElement>(null)
  const tooltipRef   = useRef<HTMLDivElement>(null)
  const cbCanvasRef  = useRef<HTMLCanvasElement>(null)
  const cbMaxRef     = useRef<HTMLSpanElement>(null)
  const cbMinRef     = useRef<HTMLSpanElement>(null)
  const layoutRef    = useRef<HeatmapLayout | null>(null)
  const lastDataRef  = useRef<HeatmapData | null>(null)
  const rangeRef     = useRef<{ start?: number; end?: number }>({})
  const [showCB,   setShowCB]   = useState(false)
  const [hasDrawn, setHasDrawn] = useState(false)

  // Keep rangeRef in sync so the resize observer can always use the latest range.
  rangeRef.current = { start: rangeStart, end: rangeEnd }

  // Reset "has drawn" state when the band changes so a blank band starts fresh.
  useEffect(() => { setHasDrawn(false); lastDataRef.current = null }, [bandId])

  // Draw when data or range changes.
  useEffect(() => {
    if (!data || !canvasRef.current) { return }
    lastDataRef.current = data
    const layout = drawHeatmap(canvasRef.current, data, rangeStart, rangeEnd)
    layoutRef.current = layout
    setLayout(layout)
    setShowCB(true)
    setHasDrawn(true)
    if (cbCanvasRef.current && cbMaxRef.current && cbMinRef.current) {
      drawColorbar(cbCanvasRef.current, layout.zMin, layout.zMax, cbMaxRef.current, cbMinRef.current)
    }
  }, [data, rangeStart, rangeEnd])

  // Resize observer — redraw on container size change
  useEffect(() => {
    const wrap = canvasRef.current?.parentElement
    if (!wrap) return
    let tid: ReturnType<typeof setTimeout>
    const ro = new ResizeObserver(() => {
      clearTimeout(tid)
      tid = setTimeout(() => {
        if (lastDataRef.current && canvasRef.current) {
          const { start, end } = rangeRef.current
          const layout = drawHeatmap(canvasRef.current, lastDataRef.current, start, end)
          layoutRef.current = layout
          setLayout(layout)
          if (cbCanvasRef.current && cbMaxRef.current && cbMinRef.current) {
            drawColorbar(cbCanvasRef.current, layout.zMin, layout.zMax, cbMaxRef.current, cbMinRef.current)
          }
        }
      }, 300)
    })
    ro.observe(wrap)
    return () => { ro.disconnect(); clearTimeout(tid) }
  }, [])

  // Mouse events
  useEffect(() => {
    const canvas  = canvasRef.current
    const cross   = crossRef.current
    const tooltip = tooltipRef.current
    if (!canvas || !cross || !tooltip) return

    function clearCross() {
      const ctx = cross!.getContext('2d')!
      ctx.clearRect(0, 0, cross!.width, cross!.height)
    }

    function drawCross(cx: number, cy: number) {
      const h = layoutRef.current
      if (!h) return
      const { left, top, plotW, plotH } = h
      const dpr = window.devicePixelRatio || 1
      if (cross!.width !== canvas!.width || cross!.height !== canvas!.height) {
        cross!.width = canvas!.width; cross!.height = canvas!.height
      }
      const ctx = cross!.getContext('2d')!
      ctx.clearRect(0, 0, cross!.width, cross!.height)
      ctx.save(); ctx.scale(dpr, dpr)
      ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = 1; ctx.setLineDash([4, 4])
      ctx.beginPath(); ctx.moveTo(left, cy);  ctx.lineTo(left + plotW, cy);  ctx.stroke()
      ctx.beginPath(); ctx.moveTo(cx,  top);  ctx.lineTo(cx,  top + plotH); ctx.stroke()
      ctx.setLineDash([]); ctx.strokeStyle = 'rgba(255,255,255,0.75)'; ctx.lineWidth = 1.5
      ctx.beginPath(); ctx.arc(cx, cy, 3, 0, Math.PI * 2); ctx.stroke()
      ctx.restore()
    }

    const onMove = (e: MouseEvent) => {
      const h = layoutRef.current
      if (!h) { clearCross(); tooltip!.style.display = 'none'; return }
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left, my = e.clientY - rect.top
      const { left, top, plotW, plotH, nTime, nFreq } = h
      if (mx < left || mx > left + plotW || my < top || my > top + plotH) {
        clearCross(); tooltip!.style.display = 'none'; return
      }
      const ti = Math.max(0, Math.min(Math.floor((mx - left) / plotW * nTime), nTime - 1))
      const fi = Math.max(0, Math.min(Math.floor((1 - (my - top) / plotH) * nFreq), nFreq - 1))
      const freq  = h.data.y[fi]
      const time  = h.data.x[ti]
      const power = h.data.z[fi]?.[ti] ?? null
      const cx = left + (ti + 0.5) / nTime * plotW
      const cy = top  + (1 - (fi + 0.5) / nFreq) * plotH
      drawCross(cx, cy)
      const freqStr  = freq  != null ? freq.toFixed(3) + ' MHz'  : '—'
      const powerStr = power != null ? power.toFixed(1) + ' dBFS' : '—'
      const timeStr  = time  ? String(time).substring(0, 19)      : '—'
      tooltip!.innerHTML =
        `<span style="color:#aaa;font-size:10px">${timeStr}</span><br>` +
        `<b style="color:#7cf">${freqStr}</b>&nbsp;&nbsp;<b style="color:#fc8">${powerStr}</b>`
      const wrapRect = canvas.parentElement!.getBoundingClientRect()
      const TW = 210
      let tx = e.clientX - wrapRect.left + 14
      let ty = e.clientY - wrapRect.top  - 44
      if (tx + TW > wrapRect.width) tx = e.clientX - wrapRect.left - TW - 10
      if (ty < 4) ty += 50
      tooltip!.style.left = tx + 'px'; tooltip!.style.top = ty + 'px'
      tooltip!.style.display = 'block'
    }

    const onLeave = () => { clearCross(); tooltip!.style.display = 'none' }

    const onClick = (e: MouseEvent) => {
      const h = layoutRef.current
      if (!h) return
      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left, my = e.clientY - rect.top
      const { left, top, plotW, plotH, nFreq } = h
      if (mx < left || mx > left + plotW || my < top || my > top + plotH) return
      const fi   = Math.max(0, Math.min(Math.floor((1 - (my - top) / plotH) * nFreq), nFreq - 1))
      const freq = h.data.y[fi]
      if (freq != null) setFreq(freq)
    }

    canvas.addEventListener('mousemove', onMove)
    canvas.addEventListener('mouseleave', onLeave)
    canvas.addEventListener('click', onClick)
    return () => {
      canvas.removeEventListener('mousemove', onMove)
      canvas.removeEventListener('mouseleave', onLeave)
      canvas.removeEventListener('click', onClick)
    }
  }, [])

  return (
    <div className="row mb-2">
      <div className="col" style={{ display: 'flex', gap: 8, alignItems: 'stretch' }}>
        <div className="heatmap-wrap" style={{ flex: 1 }}>
          <canvas className="heatmap-canvas" ref={canvasRef} />
          <canvas ref={crossRef}
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }} />
          <div className="heatmap-tooltip" ref={tooltipRef} style={{ display: 'none' }} />
          {!hasDrawn && (
            <div className="heatmap-empty">
              {!bandId ? 'No band selected' : error ? 'No data yet' : 'Loading…'}
            </div>
          )}
        </div>

        {showCB && (
          <div className="colorbar-wrap">
            <span className="colorbar-label" ref={cbMaxRef}>0</span>
            <canvas className="colorbar-canvas" ref={cbCanvasRef} />
            <span className="colorbar-label" ref={cbMinRef}>0</span>
            <span className="colorbar-label mt-1" style={{ fontSize: 10 }}>dBFS</span>
          </div>
        )}
      </div>
    </div>
  )
}
