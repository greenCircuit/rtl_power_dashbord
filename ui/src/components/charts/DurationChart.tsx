import { useEffect, useRef } from 'react'
import { Chart } from 'chart.js'
import { useStore } from '../../store'
import { useDurations } from '../../hooks/useBandData'
import { BASE_OPTS, darkScales } from '../../chartConfig'

export default function DurationChart() {
  const bandId    = useStore(s => s.bandId)
  const threshold = useStore(s => s.threshold)
  const { data }  = useDurations()
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!data || !canvasRef.current) return
    const labels = data.bins.map(v => v.toFixed(1))
    const chart = new Chart(canvasRef.current, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Count',
          data: data.counts,
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
            text: `Signal Durations above ${threshold} dBFS (n=${data.total})`,
            color: '#ccc',
          },
          tooltip: {
            callbacks: { label: ctx => `${ctx.parsed.y} transmissions` },
          },
        },
      },
    })
    return () => chart.destroy()
  }, [data])

  let emptyMsg = 'No band selected'
  if (bandId && !data) emptyMsg = 'No transmissions detected above threshold'

  return (
    <div className="chart-box" style={{ height: 260 }}>
      {!data && <div className="chart-placeholder">{emptyMsg}</div>}
      <canvas ref={canvasRef} style={{ display: data ? 'block' : 'none' }} />
    </div>
  )
}
