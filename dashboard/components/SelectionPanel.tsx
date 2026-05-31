'use client'
import { useState } from 'react'
import { useSimStore } from '../sim/state'
import SignalChart from './SignalChart'

type Tab = 'Properties' | 'Series' | 'Events'

const labelStyle: React.CSSProperties = {
  fontSize: '10px',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  color: '#3a3b3e',
}

export default function SelectionPanel() {
  const [tab, setTab] = useState<Tab>('Properties')
  const [filter, setFilter] = useState('')

  const selectedId = useSimStore(s => s.selectedId)
  const setSelectedId = useSimStore(s => s.setSelectedId)
  const relays = useSimStore(s => s.relays)
  const fobs = useSimStore(s => s.fobs)
  const drones = useSimStore(s => s.drones)
  const connections = useSimStore(s => s.connections)
  const log = useSimStore(s => s.log)
  const rfLatest = useSimStore(s => s.rfLatest)
  const rfSeries = useSimStore(s => s.rfSeries)

  if (!selectedId) return null

  const relay = relays.find(r => r.id === selectedId)
  const fob = fobs.find(f => f.id === selectedId)
  const drone = drones.find(d => d.id === selectedId)
  if (!relay && !fob && !drone) return null

  let title = selectedId
  let subtitle = ''
  const props: [string, string][] = []

  if (relay) {
    subtitle = 'Relay Node'
    const mine = connections.filter(c => c.from === relay.id || c.to === relay.id)
    const latency = mine.length ? Math.round(mine.reduce((s, c) => s + c.latency, 0) / mine.length) : 0
    const rf = rfLatest[relay.id]
    props.push(
      ['Node Id', relay.id],
      ['Status', relay.alert ? 'ALERT — threat in range' : 'ONLINE'],
      ['Latitude', relay.position[1].toFixed(5)],
      ['Longitude', relay.position[0].toFixed(5)],
      ['Comm Range', `${Math.round(relay.range)} km`],
      ['Active Links', String(relay.connections.length)],
      ['Mean Latency', `${latency} ms`],
      ['RF Signal', rf ? `${rf.rssiDbm} dBm` : '—'],
      ['RF SNR', rf ? `${rf.snrDb} dB` : '—'],
      ['Frequency', rf ? `${rf.freqMhz} MHz` : '—'],
    )
  } else if (fob) {
    subtitle = '[Asset] Command / FOB'
    const guarding = drones.filter(d => d.alive).length
    props.push(
      ['FOB Id', fob.id],
      ['Type', 'COMMAND'],
      ['Status', 'ACTIVE'],
      ['Latitude', fob.position[1].toFixed(5)],
      ['Longitude', fob.position[0].toFixed(5)],
      ['Tracking', `${guarding} hostile${guarding === 1 ? '' : 's'}`],
      ['Engagement', 'auto-intercept at range'],
    )
  } else if (drone) {
    const cls = drone.kind === 'AIR' ? 'HOSTILE UAV' : drone.kind === 'WATER' ? 'HOSTILE VESSEL' : 'HOSTILE VEHICLE'
    subtitle = `[Hostile] ${drone.kind === 'AIR' ? 'Aerial' : drone.kind === 'WATER' ? 'Surface' : 'Ground'}`
    const fob0 = fobs[0]
    const dist = fob0 ? Math.round(Math.hypot((drone.position[0] - fob0.position[0]) * 93, (drone.position[1] - fob0.position[1]) * 111)) : 0
    props.push(
      ['Track Id', drone.id],
      ['Class', cls],
      ['Status', drone.detected ? 'TRACKED' : 'INBOUND'],
      ['Target FOB', drone.targetFobId ?? '—'],
      ['Latitude', drone.position[1].toFixed(5)],
      ['Longitude', drone.position[0].toFixed(5)],
      ['Range to FOB', `${dist} km`],
      ['Engagement', drone.engaged ? 'interceptor tracking' : drone.detected ? 'firing solution' : 'pending detection'],
    )
  }

  const filtered = props.filter(([k]) => k.toLowerCase().includes(filter.toLowerCase()))
  const series = rfSeries[selectedId] ?? []
  const events = log.filter(l => l.text.includes(selectedId)).slice(-30).reverse()

  return (
    <div
      style={{
        position: 'absolute',
        top: 12,
        right: 12,
        width: '300px',
        maxHeight: 'calc(100% - 24px)',
        background: '#0c0d0f',
        border: '1px solid #1a1b1e',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 5,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '12px', borderBottom: '1px solid #1a1b1e' }}>
        <span style={{ width: 26, height: 26, background: '#111214', border: '1px solid #1a1b1e', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '12px', color: '#5a5b5e', flexShrink: 0 }}>
          {drone ? '✕' : fob ? '▣' : '◈'}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: '13px', color: '#9a9b9e', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</div>
          <div style={{ fontSize: '10px', color: '#5a5b5e', marginTop: '2px' }}>{subtitle}</div>
        </div>
        <button onClick={() => setSelectedId(null)} style={{ background: 'none', border: 'none', color: '#5a5b5e', cursor: 'pointer', fontSize: '13px', fontFamily: 'inherit' }}>✕</button>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', borderBottom: '1px solid #1a1b1e' }}>
        {(['Properties', 'Series', 'Events'] as Tab[]).map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              background: 'none',
              border: 'none',
              borderBottom: tab === t ? '1px solid #5a5b5e' : '1px solid transparent',
              color: tab === t ? '#9a9b9e' : '#3a3b3e',
              cursor: 'pointer',
              padding: '8px 12px',
              fontSize: '11px',
              fontFamily: 'inherit',
            }}
          >
            {t}{t === 'Events' && events.length ? ` ${events.length}` : ''}
          </button>
        ))}
      </div>

      <div style={{ overflowY: 'auto', flex: 1 }}>
        {tab === 'Properties' && (
          <>
            <div style={{ padding: '8px 12px', borderBottom: '1px solid #1a1b1e' }}>
              <input
                value={filter}
                onChange={e => setFilter(e.target.value)}
                placeholder="Filter..."
                spellCheck={false}
                style={{ width: '100%', background: '#08090a', border: '1px solid #1a1b1e', color: '#9a9b9e', fontFamily: 'inherit', fontSize: '11px', padding: '5px 8px' }}
              />
            </div>
            {filtered.map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', padding: '6px 12px', borderBottom: '1px solid #1a1b1e' }}>
                <span style={{ fontSize: '11px', color: '#5a5b5e', flexShrink: 0 }}>{k}</span>
                <span style={{ fontSize: '11px', color: '#9a9b9e', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{v}</span>
              </div>
            ))}
          </>
        )}

        {tab === 'Series' && (
          <div style={{ padding: '12px' }}>
            <span style={labelStyle}>RF SIGNAL — dBm</span>
            <div style={{ marginTop: '8px' }}>
              <SignalChart data={series} height={110} color="#7a3a6a" fill="#7a3a6a18" min={-100} max={-40} />
            </div>
            <span style={{ fontSize: '9px', color: '#3a3b3e', display: 'block', marginTop: '8px', lineHeight: 1.5 }}>
              {series.length ? `${series.length} samples buffered` : 'no RF samples yet — select a relay'}
            </span>
          </div>
        )}

        {tab === 'Events' && (
          <div>
            {events.length === 0 && <div style={{ padding: '10px 12px', fontSize: '10px', color: '#3a3b3e' }}>no events for this asset</div>}
            {events.map((e, i) => (
              <div key={i} style={{ padding: '5px 12px', borderBottom: '1px solid #1a1b1e', fontSize: '10px', color: e.level === 'kill' ? '#7a3a3a' : e.level === 'alert' || e.level === 'warn' ? '#7a6a3a' : '#5a5b5e' }}>
                <span style={{ color: '#3a3b3e', marginRight: '6px' }}>{e.time}</span>{e.text}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
