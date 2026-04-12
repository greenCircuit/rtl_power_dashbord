import { useEffect, useRef } from 'react'
import { useStore } from '../../store'
import { useTodActivity } from '../../hooks/useBandData'
import { ylorrdColor } from '../../colors'
import type { TodData } from '../../api'

const MARGIN = { top: 28, right: 12, bottom: 36, left: 40 }

function drawTod(canvas: HTMLCanvasElement, data: TodData) {
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
}

export default function TodHeatmap() {
  const bandId   = useStore(s => s.bandId)
  const { data } = useTodActivity()
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!data || !canvasRef.current) return
    drawTod(canvasRef.current, data)
  }, [data])

  return (
    <div className="chart-box" style={{ height: 260 }}>
      {!data && (
        <div className="chart-placeholder">
          {bandId ? 'No data yet' : 'No band selected'}
        </div>
      )}
      <canvas ref={canvasRef} style={{ display: data ? 'block' : 'none' }} />
    </div>
  )
}
