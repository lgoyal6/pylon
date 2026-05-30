import { ArcLayer } from '@deck.gl/layers'
import type { Connection } from '../sim/mesh'
import type { Relay } from '../sim/mesh'

export function buildArcLayer(connections: Connection[], relays: Relay[]) {
  const posMap = new Map(relays.map(r => [r.id, r.position]))

  return new ArcLayer({
    id: 'mesh-arcs',
    data: connections.filter(c => c.status !== 'broken'),
    getSourcePosition: (d: Connection) => posMap.get(d.from) || [0, 0],
    getTargetPosition: (d: Connection) => posMap.get(d.to) || [0, 0],
    getSourceColor: (d: Connection) =>
      d.status === 'rerouted' ? [90, 74, 106, 160] : [58, 90, 74, 160],
    getTargetColor: (d: Connection) =>
      d.status === 'rerouted' ? [90, 74, 106, 160] : [58, 90, 74, 160],
    getWidth: 1.5,
    getHeight: 0.35,
    greatCircle: false,
    widthMinPixels: 1.5,
    widthMaxPixels: 3,
    pickable: false,
  })
}
