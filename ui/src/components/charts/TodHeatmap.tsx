import { useEffect, useRef } from 'react'
import { useStore } from '../../store'
import { useTodActivity } from '../../hooks/useBandData'
import { ylorrdColor } from '../../colors'
import type { TodData } from '../../api'

const MARGIN = { top: 28, right: 48, bottom: 36, left: 40 }

interface Layout {
  left: number; top: number; plotW: number; plotH: number
  cW: number; cH: number; W0: number; H0: number
}

function drawTod(canvas: HTMLCanvasElement, data: TodData): Layout {
  const wrap = canvas.parentElement!
  const dpr  = window.devicePixelRatio || 1
  const W0   = wrap.offsetWidth  || 600
  const H0   = wrap.offsetHeight || 260
  canvas.width  = Math.round(W0 * dpr)
  canvas.height = Math.round(H0 * dpr)
  canvas.style.width  = W0 + 'px'
  canvas.style.height = H0 + 'px'

  const ctx = canvas.getContext('2d')!
  ctx.scale(dpr, dpr)

  const { top, right, bottom, left } = MARGIN
  const plotW  = W0 - left - right
  const plotH  = H0 - top  - bottom
  const nHours = 24, nDays = 7
  const cW = plotW / nHours, cH = plotH / nDays

  ctx.fillStyle = '#111'
  ctx.fillRect(0, 0, W0, H0)

  for (let d = 0; d < nDays; d++) {
    for (let h = 0; h < nHours; h++) {
      const [r, g, b] = ylorrdColor(data.z[d][h] / 100)
      ctx.fillStyle = `rgb(${r},${g},${b})`
      ctx.fillRect(left + h * cW, top + d * cH, cW, cH)
    }
  }

  ctx.strokeStyle = '#111'; ctx.lineWidth = 0.5
  for (let h = 0; h <= nHours; h++) {
    ctx.beginPath(); ctx.moveTo(left + h * cW, top); ctx.lineTo(left + h * cW, top + plotH); ctx.stroke()
  }
  for (let d = 0; d <= nDays; d++) {
    ctx.beginPath(); ctx.moveTo(left, top + d * cH); ctx.lineTo(left + plotW, top + d * cH); ctx.stroke()
  }

  ctx.fillStyle = '#ccc'; ctx.font = '11px sans-serif'
  ctx.textAlign = 'right'; ctx.textBaseline = 'middle'
  for (let d = 0; d < nDays; d++) {
    ctx.fillText(data.y[d], left - 4, top + d * cH + cH / 2)
  }

  ctx.textAlign = 'center'; ctx.textBaseline = 'top'
  for (let h = 0; h < nHours; h += 2) {
    ctx.fillText(String(h), left + h * cW + cW, top + plotH + 4)
  }

  ctx.fillStyle = '#ddd'; ctx.font = '12px sans-serif'
  ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic'
  ctx.fillText('Time-of-Day Occupancy (%)', left + plotW / 2, top - 8)
  ctx.fillStyle = '#888'; ctx.font = '10px sans-serif'
  ctx.fillText('Hour of day', left + plotW / 2, H0 - 3)

  // ── Colorbar ──────────────────────────────────────────────────────────────
  const cbX = left + plotW + 8
  const cbW = 10
  const cbH = plotH
  const steps = 50
  for (let i = 0; i < steps; i++) {
    const t = 1 - i / steps
    const [r, g, b] = ylorrdColor(t)
    ctx.fillStyle = `rgb(${r},${g},${b})`
    ctx.fillRect(cbX, top + (i / steps) * cbH, cbW, cbH / steps + 1)
  }
  ctx.strokeStyle = '#555'; ctx.lineWidth = 0.5
  ctx.strokeRect(cbX, top, cbW, cbH)

  ctx.fillStyle = '#aaa'; ctx.font = '9px sans-serif'
  ctx.textAlign = 'left'; ctx.textBaseline = 'middle'
  ctx.fillText('100%', cbX + cbW + 3, top)
  ctx.fillText('50%',  cbX + cbW + 3, top + cbH / 2)
  ctx.fillText('0%',   cbX + cbW + 3, top + cbH)

  return { left, top, plotW, plotH, cW, cH, W0, H0 }
}

export default function TodHeatmap() {
  const bandId     = useStore(s => s.bandId)
  const { data }   = useTodActivity()
  const canvasRef  = useRef<HTMLCanvasElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const layoutRef  = useRef<Layout | null>(null)
  const dataRef    = useRef<TodData | null>(null)

  useEffect(() => {
    if (!data || !canvasRef.current) return
    dataRef.current   = data
    layoutRef.current = drawTod(canvasRef.current, data)
  }, [data])

  // Redraw on container resize (e.g. fullscreen toggle)
  useEffect(() => {
    const wrap = canvasRef.current?.parentElement
    if (!wrap) return
    let tid: ReturnType<typeof setTimeout>
    const ro = new ResizeObserver(() => {
      clearTimeout(tid)
      tid = setTimeout(() => {
        if (dataRef.current && canvasRef.current)
          layoutRef.current = drawTod(canvasRef.current, dataRef.current)
      }, 50)
    })
    ro.observe(wrap)
    return () => { ro.disconnect(); clearTimeout(tid) }
  }, [])

  useEffect(() => {
    const canvas  = canvasRef.current
    const tooltip = tooltipRef.current
    if (!canvas || !tooltip) return

    const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

    const onMove = (e: MouseEvent) => {
      const layout = layoutRef.current
      const d      = dataRef.current
      if (!layout || !d) { tooltip.style.display = 'none'; return }

      const rect = canvas.getBoundingClientRect()
      const mx = e.clientX - rect.left
      const my = e.clientY - rect.top
      const { left, top, plotW, plotH, cW, cH } = layout

      if (mx < left || mx > left + plotW || my < top || my > top + plotH) {
        tooltip.style.display = 'none'; return
      }

      const h   = Math.floor((mx - left) / cW)
      const day = Math.floor((my - top)  / cH)
      if (h < 0 || h > 23 || day < 0 || day > 6) { tooltip.style.display = 'none'; return }

      const pct = d.z[day][h]
      tooltip.innerHTML =
        `<span style="color:#aaa;font-size:10px">${DAYS[day]}</span><br>` +
        `<b style="color:#7cf">${String(h).padStart(2,'0')}:00 – ${String(h+1).padStart(2,'0')}:00</b>` +
        `&nbsp;&nbsp;<b style="color:#fc8">${pct.toFixed(1)}% active</b>`

      const wrapRect = canvas.parentElement!.getBoundingClientRect()
      const TW = 200
      let tx = e.clientX - wrapRect.left + 14
      let ty = e.clientY - wrapRect.top  - 44
      if (tx + TW > wrapRect.width) tx = e.clientX - wrapRect.left - TW - 10
      if (ty < 4) ty += 50
      tooltip.style.left    = tx + 'px'
      tooltip.style.top     = ty + 'px'
      tooltip.style.display = 'block'
    }

    const onLeave = () => { tooltip.style.display = 'none' }

    canvas.addEventListener('mousemove', onMove)
    canvas.addEventListener('mouseleave', onLeave)
    return () => {
      canvas.removeEventListener('mousemove', onMove)
      canvas.removeEventListener('mouseleave', onLeave)
    }
  }, [])

  return (
    <div className="chart-box" style={{ height: 260, position: 'relative' }}>
      {!data && (
        <div className="chart-placeholder">
          {bandId ? 'No data yet' : 'No band selected'}
        </div>
      )}
      <canvas ref={canvasRef} style={{ display: data ? 'block' : 'none' }} />
      <div ref={tooltipRef} className="heatmap-tooltip" style={{ display: 'none' }} />
    </div>
  )
}
