import { ScatterplotLayer } from '@deck.gl/layers'
import type { Relay } from '../sim/mesh'
import type { Fob } from '../sim/state'

export function buildRelayLayer(relays: Relay[]) {
  return new ScatterplotLayer({
    id: 'relay-nodes',
    data: relays.filter(r => r.status !== 'offline'),
    getPosition: (d: Relay) => d.position,
    getRadius: 600,
    getFillColor: (d: Relay): [number, number, number, number] => {
      if (d.status === 'destroyed') return [58, 58, 58, 120]
      if (d.alert) return [122, 106, 58, 220]
      return [74, 106, 122, d.status === 'booting' ? 80 : 190]
    },
    radiusMinPixels: 5,
    radiusMaxPixels: 11,
    transitions: { getFillColor: 500, getRadius: 300 },
    updateTriggers: { getFillColor: relays.map(r => `${r.status}-${r.alert}`).join() },
    pickable: true,
  })
}

export function buildRingLayer(relays: Relay[]) {
  return new ScatterplotLayer({
    id: 'detection-rings',
    data: relays.filter(r => r.status === 'online'),
    getPosition: (d: Relay) => d.position,
    getRadius: (d: Relay) => d.range * 1000,
    getFillColor: [0, 0, 0, 0],
    getLineColor: (d: Relay): [number, number, number, number] =>
      d.alert ? [122, 106, 58, 60] : [74, 106, 122, 25],
    stroked: true,
    lineWidthMinPixels: 1,
    filled: false,
    pickable: false,
  })
}

// Stroked ring around the currently selected relay or FOB.
export function buildSelectionLayer(
  relays: Relay[],
  fobs: Fob[],
  selectedId: string | null
) {
  if (!selectedId) return new ScatterplotLayer({ id: 'selection', data: [] })
  const relay = relays.find(r => r.id === selectedId && r.status !== 'destroyed')
  const fob = fobs.find(f => f.id === selectedId)
  const pos = relay?.position ?? fob?.position
  if (!pos) return new ScatterplotLayer({ id: 'selection', data: [] })
  return new ScatterplotLayer({
    id: 'selection',
    data: [{ position: pos }],
    getPosition: (d: { position: [number, number] }) => d.position,
    getRadius: 1600,
    getFillColor: [0, 0, 0, 0],
    getLineColor: [154, 155, 158, 230],
    stroked: true,
    filled: false,
    lineWidthMinPixels: 1.5,
    radiusMinPixels: 12,
    radiusMaxPixels: 22,
    pickable: false,
  })
}
