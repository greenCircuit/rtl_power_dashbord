import { useRef } from 'react'
import { Chart } from 'chart.js'
import { useStore } from '../../store'
import { useActivity } from '../../hooks/useBandData'
import { useChart } from '../../hooks/useChart'
import { BASE_OPTS, darkScales } from '../../chartConfig'
import { plasmaColor } from '../../colors'
import type { ActivityData } from '../../api'

function activityColors(pcts: number[]): string[] {
  return pcts.map(pct => {
    const [r, g, b] = plasmaColor(Math.max(0, Math.min(1, pct / 100 * 0.85 + 0.05)))
    return `rgb(${r},${g},${b})`
  })
}

export default function ActivityChart() {
  const bandId    = useStore(s => s.bandId)
  const threshold = useStore(s => s.threshold)
  const { data }  = useActivity()
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useChart(
    data,
    canvasRef,
    (canvas, d) => new Chart(canvas, {
      type: 'bar',
      data: {
        labels: d.frequency_mhz,
        datasets: [{
          label: 'Active time (%)',
          data: d.activity_pct,
          backgroundColor: activityColors(d.activity_pct),
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
            callback: (v: unknown) => Number(d.frequency_mhz[v as number]).toFixed(2),
          },
        }, { min: 0, max: 100 }),
        plugins: {
          ...BASE_OPTS.plugins,
          title: { display: true, text: `Activity above ${threshold} dBFS`, color: '#ccc' },
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: items => `${Number(d.frequency_mhz[items[0].dataIndex]).toFixed(3)} MHz`,
              label:  ctx  => `Active: ${(ctx.parsed.y ?? 0).toFixed(1)}%`,
            },
          },
        },
      },
    }),
    (chart, d) => {
      chart.data.labels = d.frequency_mhz
      const ds = chart.data.datasets[0] as any
      ds.data            = d.activity_pct
      ds.backgroundColor = activityColors(d.activity_pct)
      chart.options.plugins!.title!.text = `Activity above ${threshold} dBFS`
    },
  )

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
