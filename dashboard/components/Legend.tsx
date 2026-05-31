'use client'
import { useState } from 'react'

const labelStyle: React.CSSProperties = {
  fontSize: '10px',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  color: '#3a3b3e',
}

function Row({ color, label, ring }: { color: string; label: string; ring?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '2px 0' }}>
      <span style={{
        width: 10, height: 10, flexShrink: 0,
        background: ring ? 'transparent' : color,
        border: ring ? `1px solid ${color}` : 'none',
        borderRadius: ring ? '50%' : 0,
      }} />
      <span style={{ fontSize: '10px', color: '#9a9b9e' }}>{label}</span>
    </div>
  )
}

export default function Legend() {
  const [open, setOpen] = useState(true)

  return (
    <div style={{ position: 'absolute', top: 12, left: 12, width: '188px', background: '#0c0d0f', border: '1px solid #1a1b1e', zIndex: 5 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{ width: '100%', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 10px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
      >
        <span style={labelStyle}>LEGEND</span>
        <span style={{ fontSize: '10px', color: '#5a5b5e' }}>{open ? '▴' : '▾'}</span>
      </button>

      {open && (
        <div style={{ padding: '6px 10px 10px', borderTop: '1px solid #1a1b1e' }}>
          <span style={{ ...labelStyle, display: 'block', margin: '4px 0' }}>Nodes</span>
          <Row color="rgb(74,106,122)" label="Relay" />
          <Row color="rgb(154,155,158)" label="Command / FOB" />

          <span style={{ ...labelStyle, display: 'block', margin: '8px 0 4px' }}>Mesh</span>
          <Row color="rgb(58,90,74)" label="Active link" />
          <Row color="rgb(90,74,106)" label="Rerouted link" />
          <Row color="rgb(90,150,110)" label="Signal traffic" ring />
          <Row color="rgb(230,232,236)" label="Threat alert (white)" ring />

          <span style={{ ...labelStyle, display: 'block', margin: '8px 0 4px' }}>Threat</span>
          <Row color="rgb(122,106,58)" label="Hostile — air (UAV)" />
          <Row color="rgb(90,160,200)" label="Hostile — water" />
          <Row color="rgb(176,160,80)" label="Hostile — ground" />
          <Row color="rgb(122,58,58)" label="Interceptor" />
        </div>
      )}
    </div>
  )
}
