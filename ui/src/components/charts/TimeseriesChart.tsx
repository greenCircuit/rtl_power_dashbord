import { useRef } from 'react'
import { Chart } from 'chart.js'
import { useStore } from '../../store'
import { useTimeseries } from '../../hooks/useBandData'
import { useChart } from '../../hooks/useChart'
import { BASE_OPTS, darkScales } from '../../chartConfig'
import type { TimeseriesData } from '../../api'

function create(canvas: HTMLCanvasElement, data: TimeseriesData): Chart {
  return new Chart(canvas, {
    type: 'line',
    data: {
      labels: data.timestamps.map(t => String(t).substring(11, 19)),
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
      ...BASE_OPTS,
      scales: darkScales('Time', 'Power (dBFS)'),
      plugins: {
        ...BASE_OPTS.plugins,
        title: {
          display: true,
          text: `Power over time — ${data.frequency_mhz} MHz`,
          color: '#ccc',
        },
        tooltip: {
          callbacks: { label: ctx => `${(ctx.parsed.y ?? 0).toFixed(1)} dBFS` },
        },
      },
    },
  })
}

function update(chart: Chart, data: TimeseriesData): void {
  chart.data.labels           = data.timestamps.map(t => String(t).substring(11, 19))
  chart.data.datasets[0].data = data.power_db
  ;(chart.data.datasets[0] as any).label = `${data.frequency_mhz} MHz`
  chart.options.plugins!.title!.text     = `Power over time — ${data.frequency_mhz} MHz`
}

export default function TimeseriesChart() {
  const selectedFreq        = useStore(s => s.selectedFreq)
  const { data, error }     = useTimeseries()
  const canvasRef           = useRef<HTMLCanvasElement>(null)

  useChart(data, canvasRef, create, update)

  let emptyMsg = 'Click a frequency on the heatmap to see power over time'
  if (selectedFreq != null && error) emptyMsg = `No data for ${selectedFreq.toFixed(3)} MHz`

  return (
    <div className="row mb-3">
      <div className="col">
        <div className="chart-box chart-box-sm">
          {!data && <div className="chart-placeholder">{emptyMsg}</div>}
          <canvas ref={canvasRef} style={{ display: data ? 'block' : 'none' }} />
        </div>
      </div>
    </div>
  )
}
