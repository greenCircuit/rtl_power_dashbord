import { useRef } from 'react'
import { Chart } from 'chart.js'
import { useStore } from '../../store'
import { useTopChannels } from '../../hooks/useBandData'
import { useChart } from '../../hooks/useChart'
import { BASE_OPTS, darkScales } from '../../chartConfig'
import { plasmaColor } from '../../colors'

function activityColors(pcts: number[]): string[] {
  return pcts.map(pct => {
    const [r, g, b] = plasmaColor(Math.max(0, Math.min(1, pct / 100 * 0.85 + 0.05)))
    return `rgb(${r},${g},${b})`
  })
}

export default function TopChannelsChart() {
  const bandId    = useStore(s => s.bandId)
  const threshold = useStore(s => s.threshold)
  const { data }  = useTopChannels()
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useChart(
    data,
    canvasRef,
    (canvas, d) => {
      const labels = d.frequency_mhz.map(f => f.toFixed(3))
      return new Chart(canvas, {
        type: 'bar',
        data: {
          labels,
          datasets: [{
            label: 'Active time (%)',
            data: d.activity_pct,
            backgroundColor: activityColors(d.activity_pct),
            borderWidth: 0,
          }],
        },
        options: {
          ...BASE_OPTS,
          indexAxis: 'y' as const,
          scales: darkScales('Time active (%)', 'Frequency (MHz)', {
            min: 0, max: 100,
          }, {
            ticks: { color: '#999' },
          }),
          plugins: {
            ...BASE_OPTS.plugins,
            legend: { display: false },
            title: {
              display: true,
              text: `Top Active Channels above ${threshold} dBFS`,
              color: '#ccc',
            },
            tooltip: {
              callbacks: {
                title: items => `${labels[items[0].dataIndex]} MHz`,
                label:  ctx  => [
                  `Active: ${(ctx.parsed.x ?? 0).toFixed(1)}%`,
                  `Mean:   ${d.mean_db[ctx.dataIndex].toFixed(1)} dBFS`,
                ],
              },
            },
          },
        },
      })
    },
    (chart, d) => {
      const labels = d.frequency_mhz.map(f => f.toFixed(3))
      chart.data.labels = labels
      const ds = chart.data.datasets[0] as any
      ds.data            = d.activity_pct
      ds.backgroundColor = activityColors(d.activity_pct)
      chart.options.plugins!.title!.text = `Top Active Channels above ${threshold} dBFS`
    },
  )

  return (
    <div className="chart-box" style={{ height: 300 }}>
      {!data && (
        <div className="chart-placeholder">
          {bandId ? 'No activity above threshold' : 'No band selected'}
        </div>
      )}
      <canvas ref={canvasRef} style={{ display: data ? 'block' : 'none' }} />
    </div>
  )
}
