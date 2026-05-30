import { ScatterplotLayer } from '@deck.gl/layers'
import type { Relay, Connection } from '../sim/mesh'
import type { Fob } from '../sim/state'

// Period (ms) for one signal dot to travel a link.
const SIGNAL_PERIOD_MS = 1600

function phaseOffset(id: string): number {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 997
  return (h % 100) / 100
}

interface SignalDot {
  position: [number, number]
  rerouted: boolean
}

// Small muted dots sliding along every active link to show the nodes
// continuously transmitting signals to each other. Two dots per link, offset by
// half a period, so traffic reads as a steady flow. Cheap: positions are
// computed from animationTime each frame, nothing is stored in the sim.
export function buildSignalLayer(
  connections: Connection[],
  relays: Relay[],
  fobs: Fob[],
  animationTime: number
) {
  const posMap = new Map<string, [number, number]>()
  relays.forEach(r => posMap.set(r.id, r.position))
  fobs.forEach(f => posMap.set(f.id, f.position))

  const dots: SignalDot[] = []
  for (const c of connections) {
    if (c.status !== 'active' && c.status !== 'rerouted') continue
    const a = posMap.get(c.from)
    const b = posMap.get(c.to)
    if (!a || !b) continue
    const base = (animationTime / SIGNAL_PERIOD_MS) + phaseOffset(c.id)
    for (const off of [0, 0.5]) {
      const t = (base + off) % 1
      dots.push({
        position: [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t],
        rerouted: c.status === 'rerouted',
      })
    }
  }

  return new ScatterplotLayer({
    id: 'mesh-signals',
    data: dots,
    getPosition: (d: SignalDot) => d.position,
    getRadius: 220,
    getFillColor: (d: SignalDot): [number, number, number, number] =>
      d.rerouted ? [120, 100, 140, 180] : [90, 150, 110, 180],
    radiusMinPixels: 1.5,
    radiusMaxPixels: 3,
    updateTriggers: { getPosition: animationTime },
    pickable: false,
  })
}
