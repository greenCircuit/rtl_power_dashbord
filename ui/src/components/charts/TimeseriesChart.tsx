import { useEffect, useRef } from 'react'
import { Chart } from 'chart.js'
import { useStore } from '../../store'
import { useTimeseries } from '../../hooks/useBandData'
import { BASE_OPTS, darkScales } from '../../chartConfig'

export default function TimeseriesChart() {
  const selectedFreq = useStore(s => s.selectedFreq)
  const { data, error } = useTimeseries()
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!data || !canvasRef.current) return
    const labels = data.timestamps.map(t => String(t).substring(11, 19))
    const chart = new Chart(canvasRef.current, {
      type: 'line',
      data: {
        labels,
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
            callbacks: { label: ctx => `${ctx.parsed.y.toFixed(1)} dBFS` },
          },
        },
      },
    })
    return () => chart.destroy()
  }, [data])

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
