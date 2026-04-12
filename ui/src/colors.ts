const PLASMA: [number, number, number][] = [
  [13,   8, 135],
  [75,   3, 161],
  [125,  3, 168],
  [168, 34, 150],
  [203, 70, 121],
  [229, 107, 93],
  [248, 148, 65],
  [253, 195, 40],
  [240, 243, 33],
]

const YLORRD: [number, number, number][] = [
  [255, 255, 204],
  [255, 237, 160],
  [254, 217, 118],
  [254, 178,  76],
  [253, 141,  60],
  [252,  78,  42],
  [227,  26,  28],
  [177,   0,  38],
]

function lerp(scale: [number, number, number][], t: number): [number, number, number] {
  const n = scale.length - 1
  const s = Math.max(0, Math.min(1, t)) * n
  const i = Math.floor(s)
  const f = s - i
  const a = scale[Math.min(i,     n)]
  const b = scale[Math.min(i + 1, n)]
  return [
    Math.round(a[0] + (b[0] - a[0]) * f),
    Math.round(a[1] + (b[1] - a[1]) * f),
    Math.round(a[2] + (b[2] - a[2]) * f),
  ]
}

export const plasmaColor  = (t: number) => lerp(PLASMA,  t)
export const ylorrdColor  = (t: number) => lerp(YLORRD,  t)
