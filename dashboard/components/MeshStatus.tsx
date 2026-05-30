'use client'
import { useSimStore } from '../sim/state'

export default function MeshStatus() {
  const meshHealth = useSimStore(s => s.meshHealth)

  const rows = [
    { label: 'nodes', value: `${meshHealth.nodes}/${meshHealth.totalNodes}` },
    { label: 'links', value: String(meshHealth.links) },
    { label: 'latency', value: meshHealth.latency ? `${meshHealth.latency}ms` : '--' },
    { label: 'health', value: meshHealth.health ? meshHealth.health.toFixed(2) : '0.00' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '8px 12px', borderBottom: '1px solid #1a1b1e', flexShrink: 0 }}>
        <span style={{ fontSize: '10px', letterSpacing: '0.1em', textTransform: 'uppercase', color: '#3a3b3e' }}>
          MESH STATUS
        </span>
      </div>
      <div style={{ padding: '8px 12px' }}>
        {rows.map(row => (
          <div
            key={row.label}
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '5px 0',
              borderBottom: '1px solid #1a1b1e',
            }}
          >
            <span style={{ fontSize: '10px', letterSpacing: '0.1em', textTransform: 'uppercase', color: '#3a3b3e' }}>
              {row.label}
            </span>
            <span style={{ fontSize: '12px', color: '#9a9b9e', fontVariantNumeric: 'tabular-nums' }}>
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
