import { useRef, useState } from 'react'
import { Chart } from 'chart.js'
import { useStore } from '../../store'
import { useNoiseFloor } from '../../hooks/useBandData'
import { useChart } from '../../hooks/useChart'
import { BASE_OPTS, darkScales } from '../../chartConfig'
import type { NoiseFloorData } from '../../api'

const GRANULARITIES = ['5m', '15m', '1h', '6h', '1d'] as const
type Granularity = typeof GRANULARITIES[number]

function makeDatasets(d: NoiseFloorData, gran: Granularity) {
  const pts = d.buckets.length
  const radius = pts > 60 ? 0 : 3
  return [
    {
      label: 'Noise floor (min)',
      data: d.min_db,
      borderColor: '#42a5f5',
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      borderDash: [4, 3],
      pointRadius: radius,
      tension: 0.3,
      fill: false,
      order: 3,
    },
    {
      label: 'Mean power',
      data: d.mean_db,
      borderColor: '#aaa',
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      pointRadius: radius,
      tension: 0.3,
      fill: false,
      order: 2,
    },
    {
      label: 'Peak (max)',
      data: d.max_db,
      borderColor: '#ef5350',
      // fill to dataset index 0 (noise floor) → shaded envelope
      backgroundColor: 'rgba(239,83,80,0.08)',
      borderWidth: 1.5,
      pointRadius: radius,
      tension: 0.3,
      fill: 0,
      order: 1,
    },
  ]
}

export default function NoiseFloorChart() {
  const bandId = useStore(s => s.bandId)
  const [gran, setGran] = useState<Granularity>('1h')
  const { data } = useNoiseFloor(gran)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useChart(
    data,
    canvasRef,
    (canvas, d) => new Chart(canvas, {
      type: 'line',
      data: {
        labels: d.buckets,
        datasets: makeDatasets(d, gran) as any,
      },
      options: {
        ...BASE_OPTS,
        scales: darkScales('Time', 'Power (dBFS)', {
          type: 'category',
          ticks: { color: '#999', maxTicksLimit: 10 },
        }, {
          ticks: { color: '#999' },
        }),
        plugins: {
          ...BASE_OPTS.plugins,
          title: {
            display: true,
            text: `Noise Floor & Peak Envelope [${gran}]`,
            color: '#ccc',
          },
          tooltip: {
            callbacks: {
              label: ctx =>
                `${ctx.dataset.label}: ${(ctx.parsed.y ?? 0).toFixed(1)} dBFS`,
            },
          },
        },
      },
    }),
    (chart, d) => {
      chart.data.labels = d.buckets
      const datasets = makeDatasets(d, gran)
      datasets.forEach((ds, i) => {
        const target = chart.data.datasets[i] as any
        target.data        = ds.data
        target.pointRadius = ds.pointRadius
      })
      chart.options.plugins!.title!.text = `Noise Floor & Peak Envelope [${gran}]`
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
