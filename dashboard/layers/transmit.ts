import { ScatterplotLayer } from '@deck.gl/layers'
import type { Relay } from '../sim/mesh'
import { TRANSMIT_PERIOD_MS } from '../data/config'

// Per-relay phase offset (0-1) derived from the id so pulses aren't synchronized.
function phaseOffset(id: string): number {
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) % 997
  return (h % 100) / 100
}

// Expanding "ping" ring emitted from each online relay to show active signal
// transmission. Radius grows from the node out to its range over one period,
// fading as it expands. Muted teal, in keeping with the palette.
export function buildTransmitLayer(relays: Relay[], animationTime: number) {
  const online = relays.filter(r => r.status === 'online')
  return new ScatterplotLayer({
    id: 'transmit-pulses',
    data: online,
    // include animationTime in the key inputs so deck re-evaluates accessors
    updateTriggers: {
      getRadius: animationTime,
      getLineColor: animationTime,
    },
    getPosition: (d: Relay): [number, number, number] => [d.position[0], d.position[1], d.elevation ?? 0],
    getRadius: (d: Relay) => {
      const phase = ((animationTime / TRANSMIT_PERIOD_MS) + phaseOffset(d.id)) % 1
      return phase * d.range * 1000
    },
    getFillColor: [0, 0, 0, 0],
    getLineColor: (d: Relay) => {
      const phase = ((animationTime / TRANSMIT_PERIOD_MS) + phaseOffset(d.id)) % 1
      const alpha = Math.round((1 - phase) * (d.alert ? 70 : 45))
      return d.alert ? [122, 106, 58, alpha] : [74, 106, 122, alpha]
    },
    stroked: true,
    filled: false,
    lineWidthMinPixels: 1,
    pickable: false,
  })
}
