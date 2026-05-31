'use client'
import { useSimStore } from '../sim/state'
import { SWARM_MAX_SIZE } from '../data/config'

const labelStyle: React.CSSProperties = {
  fontSize: '10px',
  letterSpacing: '0.1em',
  textTransform: 'uppercase',
  color: '#3a3b3e',
}

const btnStyle: React.CSSProperties = {
  background: '#0c0d0f',
  border: '1px solid #1a1b1e',
  color: '#9a9b9e',
  cursor: 'pointer',
  padding: '6px 10px',
  fontSize: '11px',
  letterSpacing: '0.05em',
  fontFamily: 'inherit',
  textTransform: 'uppercase',
  flex: 1,
}

const stepBtn: React.CSSProperties = {
  background: '#0c0d0f',
  border: '1px solid #1a1b1e',
  color: '#9a9b9e',
  cursor: 'pointer',
  width: '24px',
  height: '24px',
  fontSize: '12px',
  fontFamily: 'inherit',
  lineHeight: 1,
  padding: 0,
}

export default function Controls() {
  const deployRing = useSimStore(s => s.deployRing)
  const launchSwarm = useSimStore(s => s.launchSwarm)
  const reset = useSimStore(s => s.reset)
  const swarmSize = useSimStore(s => s.swarmSize)
  const setSwarmSize = useSimStore(s => s.setSwarmSize)
  const placementMode = useSimStore(s => s.placementMode)
  const setPlacementMode = useSimStore(s => s.setPlacementMode)
  const hostileType = useSimStore(s => s.hostileType)
  const setHostileType = useSimStore(s => s.setHostileType)
  const relayCount = useSimStore(s => s.relays.filter(r => r.status === 'online').length)
  const fobCount = useSimStore(s => s.fobs.length)
  const droneCount = useSimStore(s => s.drones.filter(d => d.alive).length)
  const threats = useSimStore(s => s.threatsNeutralized)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '8px 12px', borderBottom: '1px solid #1a1b1e', flexShrink: 0 }}>
        <span style={labelStyle}>CONTROLS</span>
      </div>

      <div style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {/* Deploy */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <span style={labelStyle}>Deploy</span>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button style={btnStyle} onClick={deployRing}>Deploy Ring</button>
            <button style={btnStyle} onClick={reset}>Clear</button>
          </div>

          {/* Placement mode: what a map click drops */}
          <span style={{ ...labelStyle, marginTop: '2px' }}>Click places</span>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              style={{
                ...btnStyle,
                color: placementMode === 'relay' ? '#9a9b9e' : '#3a3b3e',
                borderColor: placementMode === 'relay' ? '#3a3b3e' : '#1a1b1e',
              }}
              onClick={() => setPlacementMode('relay')}
            >Relay</button>
            <button
              style={{
                ...btnStyle,
                color: placementMode === 'fob' ? '#9a9b9e' : '#3a3b3e',
                borderColor: placementMode === 'fob' ? '#3a3b3e' : '#1a1b1e',
              }}
              onClick={() => setPlacementMode('fob')}
            >FOB</button>
            <button
              style={{
                ...btnStyle,
                color: placementMode === 'hostile' ? '#7a6a3a' : '#3a3b3e',
                borderColor: placementMode === 'hostile' ? '#3a3b3e' : '#1a1b1e',
              }}
              onClick={() => setPlacementMode('hostile')}
            >Hostile</button>
          </div>
          <span style={{ fontSize: '10px', color: '#3a3b3e', lineHeight: 1.5 }}>
            {placementMode === 'hostile'
              ? `click map to place a ${hostileType} hostile (sea = water only)`
              : `click map to place a ${placementMode === 'fob' ? 'FOB' : 'relay'} · click a relay to destroy it`}
          </span>
        </div>

        {/* Swarm */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <span style={labelStyle}>Hostile Swarm</span>
          <div style={{ display: 'flex', gap: '6px' }}>
            {(['AIR', 'WATER', 'GROUND'] as const).map(t => (
              <button
                key={t}
                onClick={() => setHostileType(t)}
                style={{
                  ...btnStyle,
                  color: hostileType === t ? '#9a9b9e' : '#3a3b3e',
                  borderColor: hostileType === t ? '#3a3b3e' : '#1a1b1e',
                }}
              >{t}</button>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              style={stepBtn}
              onClick={() => setSwarmSize(Math.max(1, swarmSize - 1))}
            >−</button>
            <span style={{ fontSize: '12px', color: '#9a9b9e', width: '28px', textAlign: 'center', fontVariantNumeric: 'tabular-nums' }}>
              {swarmSize}
            </span>
            <button
              style={stepBtn}
              onClick={() => setSwarmSize(Math.min(SWARM_MAX_SIZE, swarmSize + 1))}
            >+</button>
            <button style={{ ...btnStyle, color: '#7a6a3a' }} onClick={launchSwarm}>
              Launch Swarm
            </button>
          </div>
        </div>

        {/* Live counts */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', borderTop: '1px solid #1a1b1e', paddingTop: '8px' }}>
          <Row label="relays online" value={String(relayCount)} />
          <Row label="fobs" value={String(fobCount)} />
          <Row label="threats active" value={String(droneCount)} alert={droneCount > 0} />
          <Row label="neutralized" value={String(threats)} />
        </div>
      </div>
    </div>
  )
}

function Row({ label, value, alert }: { label: string; value: string; alert?: boolean }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={labelStyle}>{label}</span>
      <span style={{
        fontSize: '12px',
        color: alert ? '#7a6a3a' : '#9a9b9e',
        fontVariantNumeric: 'tabular-nums',
      }}>{value}</span>
    </div>
  )
}
