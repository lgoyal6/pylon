import { ScatterplotLayer } from '@deck.gl/layers'
import type { Fob } from '../sim/state'

export function buildFobLayer(fobs: Fob[]) {
  return new ScatterplotLayer({
    id: 'fobs',
    data: fobs,
    getPosition: (d: Fob): [number, number, number] => [d.position[0], d.position[1], d.elevation ?? 0],
    getRadius: 1000,
    getFillColor: [154, 155, 158, 200],
    radiusMinPixels: 6,
    radiusMaxPixels: 14,
    pickable: false,
  })
}
