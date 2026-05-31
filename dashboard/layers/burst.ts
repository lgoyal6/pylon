import { ScatterplotLayer } from '@deck.gl/layers'
import type { Burst } from '../sim/state'
import { BURST_MS, BURST_MAX_RADIUS_M } from '../data/config'

// Expanding red ring where an interceptor detonates — replaces the old straight
// intercept lines. Radius grows and fades over BURST_MS.
export function buildBurstLayer(bursts: Burst[], animationTime: number) {
  return new ScatterplotLayer({
    id: 'bursts',
    data: bursts,
    getPosition: (d: Burst): [number, number, number] => [d.position[0], d.position[1], d.elevation],
    getRadius: (d: Burst) => {
      const p = Math.min(1, (animationTime - d.startedAt) / BURST_MS)
      return p * BURST_MAX_RADIUS_M
    },
    getFillColor: [0, 0, 0, 0],
    getLineColor: (d: Burst): [number, number, number, number] => {
      const p = Math.min(1, (animationTime - d.startedAt) / BURST_MS)
      return [200, 80, 70, Math.round((1 - p) * 220)]
    },
    stroked: true,
    filled: false,
    lineWidthMinPixels: 1.5,
    lineWidthMaxPixels: 3,
    updateTriggers: { getRadius: animationTime, getLineColor: animationTime },
    pickable: false,
  })
}
