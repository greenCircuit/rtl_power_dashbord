import { useRef } from 'react'
import { Chart } from 'chart.js'
import { useStore } from '../../store'
import { useSpectrum } from '../../hooks/useBandData'
import { useChart } from '../../hooks/useChart'
import { BASE_OPTS, darkScales } from '../../chartConfig'
import type { SpectrumData } from '../../api'

function create(canvas: HTMLCanvasElement, data: SpectrumData): Chart {
  return new Chart(canvas, {
    type: 'line',
    data: {
      labels: data.frequency_mhz,
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
          label: 'Peak (window)',
          data: data.peak_db,
          borderColor: '#ff7043',
          borderWidth: 1,
          borderDash: [5, 5],
          pointRadius: 0,
          tension: 0.1,
        },
        {
          label: 'Peak (all time)',
          data: data.alltime_peak_db,
          borderColor: '#ffd54f',
          borderWidth: 1,
          borderDash: [2, 4],
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
          callback: (v: unknown) => Number(data.frequency_mhz[v as number]).toFixed(2),
        },
      }),
      plugins: {
        ...BASE_OPTS.plugins,
        title: {
          display: true,
          text: 'Mean & Peak Power per Frequency (dashed = all-time peak)',
          color: '#ccc',
        },
        tooltip: {
          callbacks: {
            title: items => `${Number(data.frequency_mhz[items[0].dataIndex]).toFixed(3)} MHz`,
            label:  ctx  => `${ctx.dataset.label}: ${(ctx.parsed.y ?? 0).toFixed(1)} dBFS`,
          },
        },
      },
    },
  })
}

function update(chart: Chart, data: SpectrumData): void {
  chart.data.labels          = data.frequency_mhz
  chart.data.datasets[0].data = data.mean_db
  chart.data.datasets[1].data = data.peak_db
  chart.data.datasets[2].data = data.alltime_peak_db
}

export default function SpectrumChart() {
  const bandId    = useStore(s => s.bandId)
  const { data }  = useSpectrum()
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useChart(data, canvasRef, create, update)

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
