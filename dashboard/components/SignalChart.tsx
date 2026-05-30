'use client'

interface Props {
  data: number[]
  height?: number
  color?: string
  fill?: string
  min?: number
  max?: number
  unit?: string
}

// Lightweight responsive SVG line chart for time-series telemetry (RF rssi, …).
// The path uses preserveAspectRatio="none" to fill width; labels are HTML
// overlays so they don't distort.
export default function SignalChart({
  data,
  height = 90,
  color = '#7a3a6a',
  fill,
  min,
  max,
  unit = '',
}: Props) {
  const VW = 1000
  const pad = 4
  const h = height

  const lo = min ?? (data.length ? Math.min(...data) : 0)
  const hi = max ?? (data.length ? Math.max(...data) : 1)
  const range = hi - lo || 1

  const pts = data.map((v, i) => {
    const x = (i / Math.max(1, data.length - 1)) * (VW - pad * 2) + pad
    const y = h - pad - ((v - lo) / range) * (h - pad * 2)
    return [x, y] as const
  })

  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ')
  const areaPath = fill && pts.length > 1
    ? `${path} L${pts[pts.length - 1][0].toFixed(1)},${h - pad} L${pts[0][0].toFixed(1)},${h - pad} Z`
    : ''

  const last = data.length ? data[data.length - 1] : null
  const labelStyle: React.CSSProperties = {
    position: 'absolute',
    fontSize: '8px',
    fontFamily: 'monospace',
    color: '#3a3b3e',
    pointerEvents: 'none',
  }

  return (
    <div style={{ position: 'relative', width: '100%', height: h }}>
      <svg width="100%" height={h} viewBox={`0 0 ${VW} ${h}`} preserveAspectRatio="none" style={{ display: 'block' }}>
        <line x1={0} y1={h - pad} x2={VW} y2={h - pad} stroke="#1a1b1e" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        <line x1={0} y1={h / 2} x2={VW} y2={h / 2} stroke="#141518" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        {fill && pts.length > 1 && <path d={areaPath} fill={fill} stroke="none" />}
        {pts.length > 1 && (
          <path d={path} fill="none" stroke={color} strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
        )}
      </svg>
      <span style={{ ...labelStyle, top: 2, left: 3 }}>{hi.toFixed(0)}{unit}</span>
      <span style={{ ...labelStyle, bottom: 2, left: 3 }}>{lo.toFixed(0)}{unit}</span>
      {last !== null && (
        <span style={{ ...labelStyle, top: 2, right: 4, color: color }}>{last.toFixed(0)}{unit}</span>
      )}
    </div>
  )
}
