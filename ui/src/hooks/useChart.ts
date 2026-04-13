import { useEffect, useRef } from 'react'
import type { RefObject } from 'react'
import { Chart } from 'chart.js'

/**
 * Creates a Chart.js instance once on first data arrival, then updates it
 * in-place on subsequent data changes — avoiding the expensive destroy/recreate
 * cycle that happens every poll interval otherwise.
 *
 * `create`  — called once when the chart is first mounted; receives the canvas
 *             and initial data; must return the new Chart instance.
 * `update`  — called on every subsequent data change; mutates chart.data and
 *             chart.options in place; the hook calls chart.update('none') after.
 *
 * Both functions are closures over the component's current render scope, so
 * they always see up-to-date state (threshold, granularity, etc.) at the time
 * data changes.
 */
export function useChart<T>(
  data: T | null,
  canvasRef: RefObject<HTMLCanvasElement | null>,
  create: (canvas: HTMLCanvasElement, data: T) => Chart,
  update: (chart: Chart, data: T) => void,
): void {
  const chartRef = useRef<Chart | null>(null)

  useEffect(() => {
    if (!data || !canvasRef.current) return
    if (!chartRef.current) {
      chartRef.current = create(canvasRef.current, data)
    } else {
      update(chartRef.current, data)
      chartRef.current.update('none')
    }
  // create/update are closures — intentionally excluded from deps.
  // The effect re-runs only when data changes, which is the correct trigger.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data])

  useEffect(() => () => { chartRef.current?.destroy() }, [])
}
