import { useRef } from 'react'
import { Chart } from 'chart.js'
import { useStore } from '../../store'
import { useDurations } from '../../hooks/useBandData'
import { useChart } from '../../hooks/useChart'
import { BASE_OPTS, darkScales } from '../../chartConfig'
import type { DurationData } from '../../api'

export default function DurationChart() {
  const bandId    = useStore(s => s.bandId)
  const threshold = useStore(s => s.threshold)
  const { data }  = useDurations()
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useChart(
    data,
    canvasRef,
    (canvas, d) => new Chart(canvas, {
      type: 'bar',
      data: {
        labels: d.bins.map(v => v.toFixed(1)),
        datasets: [{
          label: 'Count',
          data: d.counts,
          backgroundColor: '#ab47bc',
          borderWidth: 0,
          barPercentage: 1.0,
          categoryPercentage: 1.0,
        }],
      },
      options: {
        ...BASE_OPTS,
        scales: darkScales('Duration (s)', 'Count'),
        plugins: {
          ...BASE_OPTS.plugins,
          legend: { display: false },
          title: {
            display: true,
            text: `Signal Durations above ${threshold} dBFS (n=${d.total})`,
            color: '#ccc',
          },
          tooltip: {
            callbacks: { label: ctx => `${ctx.parsed.y} transmissions` },
          },
        },
      },
    }),
    (chart, d) => {
      chart.data.labels           = d.bins.map(v => v.toFixed(1))
      chart.data.datasets[0].data = d.counts
      chart.options.plugins!.title!.text = `Signal Durations above ${threshold} dBFS (n=${d.total})`
    },
  )

  let emptyMsg = 'No band selected'
  if (bandId && !data) emptyMsg = 'No transmissions detected above threshold'

  return (
    <div className="chart-box" style={{ height: 260 }}>
      {!data && <div className="chart-placeholder">{emptyMsg}</div>}
      <canvas ref={canvasRef} style={{ display: data ? 'block' : 'none' }} />
    </div>
  )
}
