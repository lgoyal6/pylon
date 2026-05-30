'use client'
import { useState } from 'react'
import { useSimStore } from '../sim/state'
import SignalChart from './SignalChart'

const SPEEDS = [0.5, 1, 2, 4]

const btn: React.CSSProperties = {
  background: 'none',
  border: '1px solid #1a1b1e',
  color: '#5a5b5e',
  cursor: 'pointer',
  padding: '3px 9px',
  fontSize: '11px',
  fontFamily: 'inherit',
  lineHeight: 1.4,
}

const labelStyle: React.CSSProperties = {
  fontSize: '10px',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  color: '#3a3b3e',
}

export default function BottomDock() {
  const playing = useSimStore(s => s.playing)
  const play = useSimStore(s => s.play)
  const pause = useSimStore(s => s.pause)
  const reset = useSimStore(s => s.reset)
  const speed = useSimStore(s => s.speed)
  const setSpeed = useSimStore(s => s.setSpeed)
  const launchSwarm = useSimStore(s => s.launchSwarm)
  const animationTime = useSimStore(s => s.animationTime)
  const droneCount = useSimStore(s => s.drones.filter(d => d.alive).length)

  const rfMode = useSimStore(s => s.rfMode)
  const rfStatus = useSimStore(s => s.rfStatus)
  const rfAggregate = useSimStore(s => s.rfAggregate)
  const rfSeries = useSimStore(s => s.rfSeries)
  const selectedId = useSimStore(s => s.selectedId)
  const connectRfSource = useSimStore(s => s.connectRfSource)
  const disconnectRfSource = useSimStore(s => s.disconnectRfSource)

  const [url, setUrl] = useState('ws://localhost:8787/rf')

  // Show the selected node's RF series if one is selected, else the aggregate.
  const series = selectedId && rfSeries[selectedId]?.length ? rfSeries[selectedId] : rfAggregate
  const seriesLabel = selectedId && rfSeries[selectedId]?.length
    ? `RF · ${selectedId}`
    : 'RF · MESH AGGREGATE'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', background: '#0c0d0f', borderTop: '1px solid #1a1b1e', flexShrink: 0 }}>
      {/* Transport header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '0 16px', height: '40px', borderBottom: '1px solid #1a1b1e' }}>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button onClick={reset} style={btn} title="Reset">◄</button>
          <button onClick={playing ? pause : play} style={btn}>{playing ? '■' : '►'}</button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{ ...labelStyle, marginRight: '4px' }}>SPEED</span>
          {SPEEDS.map(s => (
            <button key={s} onClick={() => setSpeed(s)} style={{ ...btn, color: speed === s ? '#9a9b9e' : '#3a3b3e', borderColor: speed === s ? '#3a3b3e' : '#1a1b1e' }}>{s}×</button>
          ))}
        </div>

        <span style={{ fontSize: '11px', color: '#5a5b5e', fontVariantNumeric: 'tabular-nums' }}>{formatClock(animationTime)}</span>

        <div style={{ flex: 1 }} />

        {/* RF source control */}
        <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ width: 7, height: 7, background: rfMode === 'LIVE' ? '#4a7a5a' : '#7a6a3a', display: 'inline-block' }} />
          <span style={{ ...labelStyle, color: rfMode === 'LIVE' ? '#5a5b5e' : '#3a3b3e' }}>RF · {rfMode}</span>
        </span>
        <input
          value={url}
          onChange={e => setUrl(e.target.value)}
          spellCheck={false}
          style={{ background: '#08090a', border: '1px solid #1a1b1e', color: '#9a9b9e', fontFamily: 'inherit', fontSize: '10px', padding: '3px 6px', width: '180px' }}
        />
        {rfMode === 'LIVE'
          ? <button onClick={disconnectRfSource} style={{ ...btn, color: '#7a6a3a' }}>Disconnect</button>
          : <button onClick={() => connectRfSource(url)} style={{ ...btn, color: '#9a9b9e' }}>Connect Live</button>}

        <button onClick={launchSwarm} style={{ ...btn, color: '#7a6a3a' }}>LAUNCH SWARM</button>
        <span style={{ ...labelStyle }}>{droneCount > 0 ? `[${droneCount} INBOUND]` : '[NOMINAL]'}</span>
      </div>

      {/* Series area */}
      <div style={{ display: 'flex', height: '128px' }}>
        {/* Layers / series list */}
        <div style={{ width: '190px', borderRight: '1px solid #1a1b1e', padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <span style={labelStyle}>SERIES</span>
          <SeriesRow swatch="#7a3a6a" label={seriesLabel} value={series.length ? `${series[series.length - 1]} dBm` : '—'} active />
          <SeriesRow swatch="#3a5a4a" label="MESH LINKS" value="active" />
          <SeriesRow swatch="#7a6a3a" label="THREAT TRACK" value={droneCount > 0 ? `${droneCount} live` : 'clear'} />
          <div style={{ marginTop: 'auto' }}>
            <span style={{ fontSize: '9px', color: '#3a3b3e', lineHeight: 1.4 }}>
              {rfStatus}
            </span>
          </div>
        </div>

        {/* Chart */}
        <div style={{ flex: 1, padding: '10px 14px', display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
            <span style={labelStyle}>{seriesLabel}</span>
            <span style={{ ...labelStyle }}>dBm</span>
          </div>
          <div style={{ flex: 1 }}>
            <SignalChart data={series} height={78} color="#7a3a6a" fill="#7a3a6a18" min={-100} max={-40} unit="" />
          </div>
        </div>
      </div>
    </div>
  )
}

function SeriesRow({ swatch, label, value, active }: { swatch: string; label: string; value: string; active?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <span style={{ width: 8, height: 8, background: swatch, flexShrink: 0 }} />
      <span style={{ fontSize: '10px', color: active ? '#9a9b9e' : '#5a5b5e', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{label}</span>
      <span style={{ fontSize: '10px', color: '#3a3b3e', flexShrink: 0 }}>{value}</span>
    </div>
  )
}

function formatClock(ms: number) {
  const totalSec = Math.floor(ms / 1000)
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return `T+${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
