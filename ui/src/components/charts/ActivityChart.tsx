import { useEffect, useRef } from 'react'
import { Chart } from 'chart.js'
import { useStore } from '../../store'
import { useActivity } from '../../hooks/useBandData'
import { BASE_OPTS, darkScales } from '../../chartConfig'
import { plasmaColor } from '../../colors'

export default function ActivityChart() {
  const bandId    = useStore(s => s.bandId)
  const threshold = useStore(s => s.threshold)
  const { data }  = useActivity()
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!data || !canvasRef.current) return
    const labels = data.frequency_mhz
    const bgColors = data.activity_pct.map(pct => {
      const [r, g, b] = plasmaColor(Math.max(0, Math.min(1, pct / 100 * 0.85 + 0.05)))
      return `rgb(${r},${g},${b})`
    })
    const chart = new Chart(canvasRef.current, {
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
        ...BASE_OPTS,
        scales: darkScales('Frequency (MHz)', 'Time active (%)', {
          ticks: {
            color: '#999',
            maxTicksLimit: 8,
            callback: (v: unknown) => Number(labels[v as number]).toFixed(2),
          },
        }, { min: 0, max: 100 }),
        plugins: {
          ...BASE_OPTS.plugins,
          title: { display: true, text: `Activity above ${threshold} dBFS`, color: '#ccc' },
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: items => `${Number(labels[items[0].dataIndex]).toFixed(3)} MHz`,
              label:  ctx  => `Active: ${(ctx.parsed.y ?? 0).toFixed(1)}%`,
            },
          },
        },
      },
    })
    return () => chart.destroy()
  }, [data])

  return (
    <div className="chart-box chart-box-md">
      {!data && (
        <div className="chart-placeholder">
          {bandId ? 'No data yet' : 'No band selected'}
        </div>
      )}
      <canvas ref={canvasRef} style={{ display: data ? 'block' : 'none' }} />
    </div>
  )
}
