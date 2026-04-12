import { useEffect, useRef } from 'react'
import { Chart } from 'chart.js'
import { useStore } from '../../store'
import { useSpectrum } from '../../hooks/useBandData'
import { BASE_OPTS, darkScales } from '../../chartConfig'

export default function SpectrumChart() {
  const bandId    = useStore(s => s.bandId)
  const { data }  = useSpectrum()
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (!data || !canvasRef.current) return
    const labels = data.frequency_mhz
    const chart = new Chart(canvasRef.current, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Mean power',
            data: data.mean_db,
            borderColor: '#4fc3f7',
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.1,
          },
          {
            label: 'Peak power',
            data: data.peak_db,
            borderColor: '#ff7043',
            borderWidth: 1,
            borderDash: [5, 5],
            pointRadius: 0,
            tension: 0.1,
          },
        ],
      },
      options: {
        ...BASE_OPTS,
        scales: darkScales('Frequency (MHz)', 'Power (dBFS)', {
          ticks: {
            color: '#999',
            maxTicksLimit: 8,
            callback: (v: unknown) => Number(labels[v as number]).toFixed(2),
          },
        }),
        plugins: {
          ...BASE_OPTS.plugins,
          title: { display: true, text: 'Mean & Peak Power per Frequency', color: '#ccc' },
          tooltip: {
            callbacks: {
              title: items => `${Number(labels[items[0].dataIndex]).toFixed(3)} MHz`,
              label:  ctx  => `${ctx.dataset.label}: ${(ctx.parsed.y ?? 0).toFixed(1)} dBFS`,
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
