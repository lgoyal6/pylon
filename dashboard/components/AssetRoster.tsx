'use client'
import { useState } from 'react'
import { useSimStore } from '../sim/state'
import type { Relay, Connection } from '../sim/mesh'

type Filter = 'ALL' | 'RELAY' | 'FOB' | 'HOSTILE'

interface RosterRow {
  id: string
  kind: string
  status: string
  level: 'info' | 'warn' | 'alert' | 'kill'
  detail: string
}

function relayLatency(r: Relay, connections: Connection[]): number {
  const mine = connections.filter(c => c.from === r.id || c.to === r.id)
  if (!mine.length) return 0
  return Math.round(mine.reduce((s, c) => s + c.latency, 0) / mine.length)
}

export default function AssetRoster() {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState<Filter>('ALL')

  const relays = useSimStore(s => s.relays)
  const fobs = useSimStore(s => s.fobs)
  const drones = useSimStore(s => s.drones)
  const connections = useSimStore(s => s.connections)
  const selectedId = useSimStore(s => s.selectedId)
  const setSelectedId = useSimStore(s => s.setSelectedId)

  const rows: RosterRow[] = []

  if (filter === 'ALL' || filter === 'FOB') {
    fobs.forEach(f => rows.push({
      id: f.id, kind: 'CMD', status: 'ACTIVE', level: 'info', detail: 'command node',
    }))
  }

  if (filter === 'ALL' || filter === 'RELAY') {
    relays
      .filter(r => r.status !== 'destroyed')
      .forEach(r => rows.push({
        id: r.id,
        kind: 'RLY',
        status: r.alert ? 'ALERT' : 'ONLINE',
        level: r.alert ? 'alert' : 'info',
        detail: `${r.connections.length} links · ${relayLatency(r, connections)}ms · ${Math.round(r.range)}km`,
      }))
  }

  if (filter === 'ALL' || filter === 'HOSTILE') {
    drones.filter(d => d.alive).forEach(d => {
      const fob = fobs[0]
      const dist = fob
        ? Math.round(Math.hypot(
            (d.position[0] - fob.position[0]) * 93,
            (d.position[1] - fob.position[1]) * 111))
        : 0
      rows.push({
        id: d.id, kind: 'UAV', status: d.detected ? 'TRACKED' : 'INBOUND',
        level: 'kill', detail: `${dist}km from FOB`,
      })
    })
  }

  const total = relays.filter(r => r.status !== 'destroyed').length + fobs.length + drones.filter(d => d.alive).length
  const filters: Filter[] = ['ALL', 'RELAY', 'FOB', 'HOSTILE']

  return (
    <div style={{ borderBottom: '1px solid #1a1b1e' }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 12px', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'inherit' }}
      >
        <span style={{ fontSize: '10px', letterSpacing: '0.1em', textTransform: 'uppercase', color: '#3a3b3e' }}>
          ASSETS · {total}
        </span>
        <span style={{ fontSize: '10px', color: '#5a5b5e' }}>{open ? '▴' : '▾'}</span>
      </button>

      {open && (
        <div style={{ borderTop: '1px solid #1a1b1e' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', padding: '8px 12px' }}>
            {filters.map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  background: 'none',
                  border: '1px solid #1a1b1e',
                  color: filter === f ? '#9a9b9e' : '#3a3b3e',
                  borderColor: filter === f ? '#3a3b3e' : '#1a1b1e',
                  cursor: 'pointer',
                  padding: '2px 7px',
                  fontSize: '9px',
                  letterSpacing: '0.05em',
                  fontFamily: 'inherit',
                }}
              >
                {f}
              </button>
            ))}
          </div>

          <div style={{ maxHeight: '28vh', overflowY: 'auto', borderTop: '1px solid #1a1b1e' }}>
            {rows.length === 0 && (
              <div style={{ padding: '10px 12px', fontSize: '10px', color: '#3a3b3e' }}>
                no assets — deploy relays or a ring
              </div>
            )}
            {rows.map(row => {
              const sel = row.id === selectedId
              return (
                <button
                  key={row.id}
                  onClick={() => setSelectedId(sel ? null : row.id)}
                  style={{
                    width: '100%',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '5px 12px',
                    background: sel ? '#111214' : 'none',
                    border: 'none',
                    borderBottom: '1px solid #1a1b1e',
                    borderLeft: sel ? '2px solid #5a5b5e' : '2px solid transparent',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    textAlign: 'left',
                  }}
                >
                  <span style={{ fontSize: '11px', color: '#9a9b9e', width: '46px', flexShrink: 0 }}>{row.id}</span>
                  <span style={{ fontSize: '9px', color: '#5a5b5e', width: '30px', flexShrink: 0, letterSpacing: '0.05em' }}>{row.kind}</span>
                  <span style={{
                    fontSize: '9px', width: '52px', flexShrink: 0,
                    color: row.level === 'kill' ? '#7a3a3a' : row.level === 'alert' ? '#7a6a3a' : '#5a5b5e',
                  }}>{row.status}</span>
                  <span style={{ fontSize: '10px', color: '#3a3b3e', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{row.detail}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
