import { LineLayer, ScatterplotLayer } from '@deck.gl/layers'
import type { InterceptLine, Fob } from '../sim/state'

export function buildInterceptLayer(lines: InterceptLine[]) {
  return new LineLayer({
    id: 'intercept-lines',
    data: lines,
    getSourcePosition: (d: InterceptLine) => d.from,
    getTargetPosition: (d: InterceptLine) => d.to,
    getColor: [122, 58, 58, 200],
    getWidth: 2,
    widthMinPixels: 1,
    pickable: false,
  })
}

export function buildFobLayer(fobs: Fob[]) {
  return new ScatterplotLayer({
    id: 'fobs',
    data: fobs,
    getPosition: (d: Fob) => d.position,
    getRadius: 1000,
    getFillColor: [154, 155, 158, 200],
    radiusMinPixels: 6,
    radiusMaxPixels: 14,
    pickable: false,
  })
}
