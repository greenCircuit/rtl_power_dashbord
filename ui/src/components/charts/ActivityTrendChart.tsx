import { useRef, useState } from 'react'
import { Chart } from 'chart.js'
import { useStore } from '../../store'
import { useActivityTrend } from '../../hooks/useBandData'
import { useChart } from '../../hooks/useChart'
import { BASE_OPTS, darkScales } from '../../chartConfig'

const GRANULARITIES = ['5m', '15m', '1h', '6h', '1d'] as const
type Granularity = typeof GRANULARITIES[number]

export default function ActivityTrendChart() {
  const bandId    = useStore(s => s.bandId)
  const threshold = useStore(s => s.threshold)
  const [gran, setGran] = useState<Granularity>('1h')
  const { data }  = useActivityTrend(gran)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useChart(
    data,
    canvasRef,
    (canvas, d) => new Chart(canvas, {
      type: 'line',
      data: {
        labels: d.buckets,
        datasets: [{
          label: 'Activity (%)',
          data: d.activity_pct,
          borderColor: '#66bb6a',
          backgroundColor: 'rgba(102,187,106,0.15)',
          borderWidth: 2,
          pointRadius: d.buckets.length > 60 ? 0 : 3,
          tension: 0.3,
          fill: true,
        }],
      },
      options: {
        ...BASE_OPTS,
        scales: darkScales('Time', 'Activity (%)', {
          type: 'category',
          ticks: { color: '#999', maxTicksLimit: 10 },
        }, {
          min: 0, max: 100,
          ticks: { color: '#999' },
        }),
        plugins: {
          ...BASE_OPTS.plugins,
          title: {
            display: true,
            text: `Band Activity Trend [${gran}]  above ${threshold} dBFS`,
            color: '#ccc',
          },
          tooltip: {
            callbacks: {
              label: ctx => `Active: ${(ctx.parsed.y ?? 0).toFixed(1)}%`,
            },
          },
        },
      },
    }),
    (chart, d) => {
      chart.data.labels = d.buckets
      const ds = chart.data.datasets[0] as any
      ds.data        = d.activity_pct
      ds.pointRadius = d.buckets.length > 60 ? 0 : 3
      chart.options.plugins!.title!.text = `Band Activity Trend [${gran}]  above ${threshold} dBFS`
    },
  )

  return (
    <div className="chart-box" style={{ height: 260 }}>
      <div style={{ position: 'absolute', top: 6, left: 8, zIndex: 1 }}>
        <div className="btn-group btn-group-sm">
          {GRANULARITIES.map(g => (
            <button
              key={g}
              className={`btn btn-outline-secondary${gran === g ? ' active' : ''}`}
              style={{ fontFamily: 'monospace', fontSize: '0.7rem', padding: '1px 6px' }}
              onClick={() => setGran(g)}
            >
              [{g}]
            </button>
          ))}
        </div>
      </div>

      {!data && (
        <div className="chart-placeholder">
          {bandId ? `No data yet — waiting for [${gran}] bucket to fill` : 'No band selected'}
        </div>
      )}
      <canvas ref={canvasRef} style={{ display: data ? 'block' : 'none' }} />
    </div>
  )
}
