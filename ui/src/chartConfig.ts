export const BASE_OPTS = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false as const,
  plugins: {
    legend: { labels: { color: '#ccc', boxWidth: 12 } },
  },
}

export function darkScales(
  xLabel: string,
  yLabel: string,
  extraX: object = {},
  extraY: object = {},
) {
  return {
    x: {
      ticks: { color: '#999', maxTicksLimit: 8 },
      grid:  { color: '#222' },
      title: { display: !!xLabel, text: xLabel, color: '#888' },
      ...extraX,
    },
    y: {
      ticks: { color: '#999' },
      grid:  { color: '#222' },
      title: { display: !!yLabel, text: yLabel, color: '#888' },
      ...extraY,
    },
  }
}
