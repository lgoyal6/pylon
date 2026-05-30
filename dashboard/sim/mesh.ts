export interface Relay {
  id: string
  position: [number, number]
  range: number
  status: 'offline' | 'booting' | 'online' | 'destroyed'
  connections: string[]
  alert?: boolean
}

export interface Connection {
  id: string
  from: string
  to: string
  status: 'forming' | 'active' | 'broken' | 'rerouted'
  latency: number
}

export function distanceKm(a: [number, number], b: [number, number]): number {
  const dlat = (b[1] - a[1]) * 111
  const dlng = (b[0] - a[0]) * 111 * Math.cos((a[1] * Math.PI) / 180)
  return Math.sqrt(dlat * dlat + dlng * dlng)
}

export function placeRelays(
  fobPosition: [number, number],
  count: number,
  minRadius: number,
  maxRadius: number
): Relay[] {
  const relays: Relay[] = []
  // Use seeded-like values for consistency per session
  for (let i = 0; i < count; i++) {
    const angle = (2 * Math.PI * i) / count + (Math.random() - 0.5) * 0.4
    const radius = minRadius + Math.random() * (maxRadius - minRadius)
    const lng = fobPosition[0] + (radius / 111) * Math.cos(angle)
    const lat = fobPosition[1] + (radius / 111) * Math.sin(angle)
    relays.push({
      id: `R-${String(i + 1).padStart(2, '0')}`,
      position: [lng, lat],
      range: 22 + Math.random() * 8,
      status: 'offline',
      connections: [],
    })
  }
  return relays
}

export function formConnections(relays: Relay[]): Connection[] {
  const connections: Connection[] = []
  const onlineRelays = relays.filter(r => r.status === 'online')

  // Reset connections arrays
  onlineRelays.forEach(r => { r.connections = [] })

  for (let i = 0; i < onlineRelays.length; i++) {
    for (let j = i + 1; j < onlineRelays.length; j++) {
      const a = onlineRelays[i]
      const b = onlineRelays[j]
      const dist = distanceKm(a.position, b.position)
      if (dist <= Math.min(a.range, b.range)) {
        connections.push({
          id: `${a.id}-${b.id}`,
          from: a.id,
          to: b.id,
          status: 'active',
          latency: Math.round(dist * 0.3 + Math.random() * 5),
        })
        a.connections.push(b.id)
        b.connections.push(a.id)
      }
    }
  }
  return connections
}

export function destroyRelay(
  relayId: string,
  relays: Relay[],
  connections: Connection[]
): { relays: Relay[]; connections: Connection[] } {
  const updatedRelays = relays.map(r =>
    r.id === relayId ? { ...r, status: 'destroyed' as const, connections: [] } : r
  )
  updatedRelays.forEach(r => {
    if (r.id !== relayId) {
      r.connections = r.connections.filter(id => id !== relayId)
    }
  })
  const survivingConnections = connections.filter(
    c => c.from !== relayId && c.to !== relayId
  )
  return { relays: updatedRelays, connections: survivingConnections }
}

export function healMesh(
  relays: Relay[],
  previousConnections: Connection[]
): Connection[] {
  const previousIds = new Set(previousConnections.map(c => c.id))
  const onlineRelays = relays.filter(r => r.status === 'online')
  const newConnections = formConnections(onlineRelays)
  newConnections.forEach(c => {
    if (!previousIds.has(c.id)) {
      c.status = 'rerouted'
    }
  })
  return newConnections
}
