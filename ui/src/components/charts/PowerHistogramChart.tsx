import { useRef } from 'react'
import { Chart } from 'chart.js'
import { useStore } from '../../store'
import { usePowerHistogram } from '../../hooks/useBandData'
import { useChart } from '../../hooks/useChart'
import { BASE_OPTS, darkScales } from '../../chartConfig'
import type { PowerHistogramData } from '../../api'

function titleText(data: PowerHistogramData): string {
  return `Power Distribution  (n=${data.total.toLocaleString()}  range: ${data.min_db} – ${data.max_db} dBFS)`
}

function create(canvas: HTMLCanvasElement, data: PowerHistogramData): Chart {
  return new Chart(canvas, {
    type: 'bar',
    data: {
      labels: data.bins.map(v => v.toFixed(1)),
      datasets: [{
        label: 'Readings',
        data: data.counts,
        backgroundColor: '#26c6da',
        borderWidth: 0,
        barPercentage: 1.0,
        categoryPercentage: 1.0,
      }],
    },
    options: {
      ...BASE_OPTS,
      scales: darkScales('Power (dBFS)', 'Count', {
        ticks: {
          color: '#999',
          maxTicksLimit: 10,
          callback: (v: unknown) => Number(data.bins[v as number]).toFixed(0),
        },
      }),
      plugins: {
        ...BASE_OPTS.plugins,
        legend: { display: false },
        title: { display: true, text: titleText(data), color: '#ccc' },
        tooltip: {
          callbacks: {
            title: items => `${data.bins[items[0].dataIndex].toFixed(1)} dBFS`,
            label:  ctx  => `${(ctx.parsed.y ?? 0).toLocaleString()} readings`,
          },
        },
      },
    },
  })
}

function update(chart: Chart, data: PowerHistogramData): void {
  chart.data.labels           = data.bins.map(v => v.toFixed(1))
  chart.data.datasets[0].data = data.counts
  chart.options.plugins!.title!.text = titleText(data)
}

export default function PowerHistogramChart() {
  const bandId    = useStore(s => s.bandId)
  const { data }  = usePowerHistogram()
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useChart(data, canvasRef, create, update)

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
