import { useState, useEffect } from 'react'

interface Props {
  children: React.ReactNode
}

export default function ChartFullscreen({ children }: Props) {
  const [fullscreen, setFullscreen] = useState(false)

  useEffect(() => {
    if (!fullscreen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setFullscreen(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [fullscreen])

  return (
    <div className={`chart-fs-wrap${fullscreen ? ' is-fullscreen' : ''}`}>
      <button
        className="chart-fs-btn"
        onClick={() => setFullscreen(f => !f)}
        title={fullscreen ? 'Exit fullscreen (Esc)' : 'Fullscreen'}
      >
        {fullscreen ? '✕' : '⛶'}
      </button>
      {children}
    </div>
  )
}
